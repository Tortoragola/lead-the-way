import streamlit as st
import pandas as pd
from google import genai
import json
import os
import re

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Lead The Way – AI B2B Filtre",
    page_icon="🎯",
    layout="wide",
)

# ── Helpers ──────────────────────────────────────────────────────────────────

DEFAULT_CSV = os.path.join(
    os.path.dirname(__file__),
    "Bones - People Inside Businesses Data Sample.csv",
)

NUMERIC_COLS = {"# Employees", "Annual Revenue", "Total Funding", "Latest Funding Amount"}

OPERATORS = {
    "contains":      lambda s, v: s.astype(str).str.contains(v, case=False, na=False),
    "not_contains":  lambda s, v: ~s.astype(str).str.contains(v, case=False, na=False),
    "equals":        lambda s, v: s.astype(str).str.lower() == str(v).lower(),
    "not_equals":    lambda s, v: s.astype(str).str.lower() != str(v).lower(),
    "starts_with":   lambda s, v: s.astype(str).str.lower().str.startswith(str(v).lower()),
    "ends_with":     lambda s, v: s.astype(str).str.lower().str.endswith(str(v).lower()),
    "greater_than":  lambda s, v: pd.to_numeric(s, errors="coerce") > float(v),
    "less_than":     lambda s, v: pd.to_numeric(s, errors="coerce") < float(v),
    "in_list":       lambda s, v: s.astype(str).str.lower().isin([x.lower() for x in (v if isinstance(v, list) else [v])]),
}


@st.cache_data
def load_default_csv() -> pd.DataFrame:
    return pd.read_csv(DEFAULT_CSV, low_memory=False)


def sample_values(df: pd.DataFrame, col: str, n: int = 3) -> str:
    vals = df[col].dropna().astype(str)
    vals = vals[vals.str.strip() != ""]
    sample = vals.head(n).tolist()
    return " | ".join(sample) if sample else "N/A"


def build_gemini_prompt(query: str, df: pd.DataFrame) -> str:
    col_lines = []
    for col in df.columns:
        ex = sample_values(df, col)
        # Trim long examples (e.g. Keywords column)
        if len(ex) > 120:
            ex = ex[:120] + "…"
        col_lines.append(f'  "{col}": örnek → {ex}')
    columns_block = "\n".join(col_lines)

    return f"""Sen bir B2B iletişim veritabanı filtreleme asistanısın.
Kullanıcının doğal dildeki arama sorgusunu, aşağıdaki CSV sütunlarını kullanarak JSON filtre kurallarına çevir.

## CSV Sütunları ve Örnek Değerleri
{columns_block}

## Kullanıcı Sorgusu
"{query}"

## Talimatlar
- Yalnızca geçerli sütun adlarını kullan (yukarıdaki listeden).
- Her kural bir "column", "operator" ve "value" içermelidir.
- Desteklenen operatörler: contains, not_contains, equals, not_equals, starts_with, ends_with, greater_than, less_than, in_list
- "in_list" için "value" bir liste olmalıdır.
- Birden fazla kural için "logic" alanı "AND" ya da "OR" olabilir (varsayılan AND).
- Türkçe ve İngilizce terimler eşdeğer kabul edilmelidir (örn. "pazarlama" → "marketing").
- Sadece JSON döndür, başka açıklama ekleme.

## Beklenen JSON formatı
{{
  "filters": [
    {{"column": "<sütun_adı>", "operator": "<operatör>", "value": "<değer>"}}
  ],
  "logic": "AND"
}}
"""


def extract_json(text: str) -> dict:
    """Extract JSON object from Gemini's response text."""
    # Try direct parse first
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # Find JSON block inside markdown fences or bare braces
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    raise ValueError("Gemini yanıtından JSON ayrıştırılamadı.")


def apply_filters(df: pd.DataFrame, filter_spec: dict) -> pd.DataFrame:
    filters = filter_spec.get("filters", [])
    logic = filter_spec.get("logic", "AND").upper()

    if not filters:
        return df

    masks = []
    for rule in filters:
        col = rule.get("column", "").strip()
        op = rule.get("operator", "contains").strip()
        val = rule.get("value", "")

        if col not in df.columns:
            st.warning(f"⚠️ Sütun bulunamadı: **{col}** — bu kural atlandı.")
            continue
        if op not in OPERATORS:
            st.warning(f"⚠️ Bilinmeyen operatör: **{op}** — bu kural atlandı.")
            continue

        try:
            mask = OPERATORS[op](df[col], val)
            masks.append(mask)
        except Exception as e:
            st.warning(f"⚠️ Filtre uygulanamadı ({col} {op} {val}): {e}")

    if not masks:
        return df

    combined = masks[0]
    for m in masks[1:]:
        combined = combined & m if logic == "AND" else combined | m

    return df[combined]


# ── UI Layout ────────────────────────────────────────────────────────────────

st.title("🎯 Lead The Way — AI B2B Lead Filtresi")
st.caption("Doğal dilde yazın, Gemini AI ilgili kişileri otomatik filtrelesin.")

# Sidebar
with st.sidebar:
    st.header("⚙️ Ayarlar")
    api_key = st.text_input(
        "Gemini API Anahtarı",
        type="password",
        help="Google AI Studio → https://aistudio.google.com/app/apikey adresinden ücretsiz alabilirsiniz.",
    )
    st.markdown("---")
    uploaded_file = st.file_uploader(
        "CSV Dosyası Yükle (opsiyonel)",
        type=["csv"],
        help="Boş bırakırsanız varsayılan örnek CSV kullanılır.",
    )
    st.markdown("---")
    st.markdown(
        "**Örnek sorgular:**\n"
        "- Türkiye'deki pazarlama müdürlerini bul\n"
        "- İstanbul'da fintech sektöründeki C-level yöneticiler\n"
        "- 1000'den fazla çalışanı olan Teknoloji şirketlerindeki data scientist'lar\n"
        "- Bankacılık sektöründeki kıdemli mühendisler\n"
        "- Microsoft teknolojisi kullanan şirketler"
    )

# ── API Key check ─────────────────────────────────────────────────────────────
if not api_key:
    st.info("👈 Lütfen sol panelden **Gemini API anahtarınızı** girin.")
    st.stop()

try:
    gemini_client = genai.Client(api_key=api_key)
except Exception as e:
    st.error(f"API yapılandırma hatası: {e}")
    st.stop()

# ── Load data ─────────────────────────────────────────────────────────────────
try:
    if uploaded_file:
        df_full = pd.read_csv(uploaded_file, low_memory=False)
    else:
        df_full = load_default_csv()
except Exception as e:
    st.error(f"CSV yüklenirken hata oluştu: {e}")
    st.stop()

# Dataset overview
col_a, col_b, col_c = st.columns(3)
col_a.metric("Toplam Kişi", len(df_full))
col_b.metric("Sütun Sayısı", len(df_full.columns))
col_c.metric("Ülke Sayısı", df_full["Country"].nunique() if "Country" in df_full.columns else "—")

st.markdown("---")

# ── Natural language query ────────────────────────────────────────────────────
query = st.text_input(
    "🔍 Arama Sorgunuz",
    placeholder="Örn: Türkiye'deki pazarlama müdürlerini bul",
    label_visibility="visible",
)

display_cols = st.multiselect(
    "Gösterilecek Sütunlar",
    options=list(df_full.columns),
    default=["First Name", "Last Name", "Title", "Company Name", "Seniority",
             "Departments", "Industry", "City", "Country", "Email"],
    help="Sonuç tablosunda hangi sütunların görüneceğini seçin.",
)

if st.button("🚀 Filtrele", type="primary", disabled=not query):
    with st.spinner("Gemini AI filtreyi oluşturuyor…"):
        try:
            prompt = build_gemini_prompt(query, df_full)
            response = gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            raw_text = response.text
        except Exception as e:
            st.error(f"Gemini API hatası: {e}")
            st.stop()

    # Show raw AI response in expander for transparency
    with st.expander("🤖 Gemini'nin Ürettiği Filtre Kuralları (JSON)", expanded=False):
        st.code(raw_text, language="json")

    try:
        filter_spec = extract_json(raw_text)
    except ValueError as e:
        st.error(f"JSON ayrıştırma hatası: {e}\n\nHam yanıt:\n{raw_text}")
        st.stop()

    # Show parsed filters as a readable table
    if filter_spec.get("filters"):
        st.subheader("📋 Uygulanan Filtreler")
        filter_df = pd.DataFrame(filter_spec["filters"])
        st.dataframe(filter_df, use_container_width=True, hide_index=True)
        st.caption(f"Mantık: **{filter_spec.get('logic', 'AND')}**")

    # Apply filters
    df_filtered = apply_filters(df_full, filter_spec)

    st.markdown("---")
    st.subheader(f"✅ Sonuçlar — {len(df_filtered)} kişi bulundu")

    if df_filtered.empty:
        st.warning("Arama kriterlerine uyan kayıt bulunamadı. Sorgunuzu genişletmeyi deneyin.")
    else:
        # Display table
        show_cols = [c for c in display_cols if c in df_filtered.columns] or list(df_filtered.columns)
        st.dataframe(df_filtered[show_cols], use_container_width=True, hide_index=True)

        # Download button
        csv_out = df_filtered.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="⬇️ Sonuçları CSV olarak indir",
            data=csv_out,
            file_name="filtered_leads.csv",
            mime="text/csv",
        )

# ── Footer: raw data preview ──────────────────────────────────────────────────
with st.expander("📂 Ham Veri Önizlemesi (ilk 5 satır)", expanded=False):
    st.dataframe(df_full.head(), use_container_width=True)
