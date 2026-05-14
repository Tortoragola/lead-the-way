"""Prompt builders kept separate from call sites."""
from __future__ import annotations

import pandas as pd

from ..data import sample_values
from ..config import PRODUCT_DESCRIPTION
from ..models import CompanyIntentProfile


def build_system_prompt(df: pd.DataFrame) -> str:
    col_lines = [f'  "{col}": örnek → {sample_values(df, col)}' for col in df.columns]
    return (
        "Sen bir B2B iletişim veritabanı filtreleme asistanısın.\n"
        "Kullanıcının doğal dildeki sorgusunu analiz ederek filter_dataframe fonksiyonunu çağır.\n"
        "Türkçe terimleri İngilizce karşılıklarına çevir (pazarlama→marketing, müdür→manager, vb.).\n\n"
        "FİLTRE STRATEJİSİ (kritik kurallar):\n"
        "1. Title, Departments, Industry, Technologies, Keywords sütunlarında DAIMA `contains` kullan — asla `equals` değil.\n"
        "   Neden: hücreler 'Marketing, Sales' gibi birleşik olabilir; `equals` bunları kaçırır.\n"
        "2. Country ve Seniority için `equals` veya `in_list` uygundur.\n"
        "3. Unvan+departman kombinasyonunda (örn. 'pazarlama müdürü'):\n"
        "   YANLIŞ: [Title contains 'Manager'] AND [Departments equals 'Marketing']\n"
        "   DOĞRU : [Title contains 'Marketing Manager'] — tek filtre, tam ifadeyle\n"
        "   YA DA  : [Title contains 'Marketing Manager'] OR [Departments contains 'Marketing'] — OR logic\n"
        "4. Hem Title hem Departments filtreliyorsan OR logic kullan, AND değil;\n"
        "   çünkü unvanı 'Marketing Manager' olan ama departmanı farklı etiketlenmiş kişiler AND ile kaybolur.\n\n"
        "Mevcut CSV sütunları ve örnek değerleri:\n"
        + "\n".join(col_lines)
    )


def build_outreach_prompt(
    person: dict,
    intent_profile: CompanyIntentProfile | None = None,
) -> str:
    first    = person.get("First Name", "")
    last     = person.get("Last Name", "")
    title    = person.get("Title", "")
    company  = person.get("Company Name", "")
    industry = person.get("Industry", "")
    city     = person.get("City", "")
    country  = person.get("Country", "")
    email    = person.get("Email", "")
    employees = person.get("# Employees", "")

    if intent_profile and intent_profile.intent_signals:
        signals_block = "\n".join(f"- {s}" for s in intent_profile.intent_signals)
        intent_section = f"""

GERÇEK NİYET SİNYALLERİ (Google ile doğrulanmış, son 90 gün):
Skor: {intent_profile.intent_score}/10 ({intent_profile.intent_level.value})
{signals_block}

ÖNEMLİ: 1. görevde (intent) bu gerçek sinyallerden en güçlüsünü tek cümlede özetle.
Sentetik/uydurma sinyaller üretme.
"""
    else:
        intent_section = ""

    return f"""Sen deneyimli bir B2B satış uzmanısın.

Ürünümüz: {PRODUCT_DESCRIPTION}

Hedef kişi bilgileri:
- Ad Soyad : {first} {last}
- Unvan    : {title}
- Şirket   : {company}
- Sektör   : {industry}
- Konum    : {city}, {country}
- Çalışan  : {employees}
- E-posta  : {email}
{intent_section}
İki görevin var:

1. SATIN ALMA NİYETİ (intent):
Bu şirketin neden ürünümüze ihtiyaç duyabileceğine dair gerçekçi, inandırıcı, spesifik ve tek cümlelik bir "Satın Alma Niyeti" yaz. Sektöre ve şirkete özgü olsun, genel kalıplardan kaçın.

2. SOĞUK SATIŞ MAİLİ (email_draft):
Bu niyet verisini de kullanarak {first}'e özel, ikna edici, profesyonel ve kısa (3-4 paragraf) bir İngilizce soğuk satış maili yaz. Konu satırını (Subject:) en üste ekle. Şirket adını ve unvanını doğal şekilde kullan. Maili "Best regards,\\nLead The Way Team" ile bitir.
"""
