import streamlit as st
import pandas as pd
from google import genai
from google.genai import types
import json
import os

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Lead The Way – AI B2B SDR",
    page_icon="🎯",
    layout="wide",
)

# ── Constants ────────────────────────────────────────────────────────────────

# ✏️  Ürününüzü buradan değiştirin
PRODUCT_DESCRIPTION = (
    "Lead The Way: Şirketlerin doğal dil komutlarıyla B2B iletişim "
    "veritabanlarını anlık filtreleyip, yapay zeka destekli kişiselleştirilmiş "
    "soğuk satış mesajları oluşturmasını sağlayan AI-native satış zekası platformu."
)

DEFAULT_CSV = os.path.join(
    os.path.dirname(__file__),
    "Bones - People Inside Businesses Data Sample.csv",
)

OPERATORS = {
    "contains":     lambda s, v: s.astype(str).str.contains(str(v), case=False, na=False),
    "not_contains": lambda s, v: ~s.astype(str).str.contains(str(v), case=False, na=False),
    "equals":       lambda s, v: s.astype(str).str.lower() == str(v).lower(),
    "not_equals":   lambda s, v: s.astype(str).str.lower() != str(v).lower(),
    "starts_with":  lambda s, v: s.astype(str).str.lower().str.startswith(str(v).lower()),
    "ends_with":    lambda s, v: s.astype(str).str.lower().str.endswith(str(v).lower()),
    "greater_than": lambda s, v: pd.to_numeric(s, errors="coerce") > float(v),
    "less_than":    lambda s, v: pd.to_numeric(s, errors="coerce") < float(v),
    "in_list":      lambda s, v: s.astype(str).str.lower().isin(
                        [x.strip().lower() for x in (v.split(",") if isinstance(v, str) else v)]
                    ),
}

# ── Gemini Function Calling Tool Definition ──────────────────────────────────

FILTER_DATAFRAME_TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="filter_dataframe",
            description=(
                "B2B iletişim veritabanını verilen kriterlere göre filtreler. "
                "Kullanıcının doğal dildeki isteğini sütun bazlı filtre kurallarına dönüştür."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "filters": types.Schema(
                        type=types.Type.ARRAY,
                        description="Uygulanacak filtre kuralları listesi",
                        items=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "column": types.Schema(
                                    type=types.Type.STRING,
                                    description=(
                                        "Filtrelenecek sütun adı. Geçerli değerler: "
                                        "First Name, Last Name, Title, Company Name, Email, "
                                        "Seniority, Departments, Sub Departments, Industry, "
                                        "City, State, Country, Company City, Company Country, "
                                        "# Employees, Annual Revenue, Technologies, Keywords"
                                    ),
                                ),
                                "operator": types.Schema(
                                    type=types.Type.STRING,
                                    description="Filtre operatörü",
                                    enum=[
                                        "contains", "not_contains", "equals", "not_equals",
                                        "starts_with", "ends_with", "greater_than", "less_than",
                                        "in_list",
                                    ],
                                ),
                                "value": types.Schema(
                                    type=types.Type.STRING,
                                    description=(
                                        "Filtre değeri. in_list için virgülle ayrılmış değerler. "
                                        "Türkçe terimler otomatik olarak İngilizce karşılıklarıyla eşleştirilir "
                                        "(örn. 'pazarlama' → 'marketing', 'müdür' → 'manager')."
                                    ),
                                ),
                            },
                            required=["column", "operator", "value"],
                        ),
                    ),
                    "logic": types.Schema(
                        type=types.Type.STRING,
                        description="Filtreler arası mantık operatörü",
                        enum=["AND", "OR"],
                    ),
                },
                required=["filters"],
            ),
        )
    ]
)

# ── Data helpers ─────────────────────────────────────────────────────────────

@st.cache_data
def load_default_csv() -> pd.DataFrame:
    return pd.read_csv(DEFAULT_CSV, low_memory=False)


def sample_values(df: pd.DataFrame, col: str, n: int = 5) -> str:
    vals = df[col].dropna().astype(str)
    vals = vals[vals.str.strip() != ""]
    sample = vals.head(n).tolist()
    ex = " | ".join(sample)
    return ex[:150] + "…" if len(ex) > 150 else ex


def build_system_prompt(df: pd.DataFrame) -> str:
    col_lines = [f'  "{col}": örnek → {sample_values(df, col)}' for col in df.columns]
    return (
        "Sen bir B2B iletişim veritabanı filtreleme asistanısın.\n"
        "Kullanıcının doğal dildeki sorgusunu analiz ederek filter_dataframe fonksiyonunu çağır.\n"
        "Türkçe terimleri İngilizce karşılıklarına çevir (pazarlama→marketing, müdür→manager, vb.).\n\n"
        "Mevcut CSV sütunları ve örnek değerleri:\n"
        + "\n".join(col_lines)
    )


def filter_dataframe(df: pd.DataFrame, filters: list, logic: str = "AND") -> pd.DataFrame:
    """Execute filter_dataframe function call result on the dataframe."""
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
            masks.append(OPERATORS[op](df[col], val))
        except Exception as e:
            st.warning(f"⚠️ Filtre hatası ({col} {op} {val}): {e}")

    if not masks:
        return df

    combined = masks[0]
    for m in masks[1:]:
        combined = combined & m if logic.upper() == "AND" else combined | m

    return df[combined]


def generate_outreach(client: genai.Client, person: dict) -> dict:
    """
    Gemini'den iki şey üret:
      1. Sentetik Satın Alma Niyeti (tek cümle)
      2. Kişiye özel soğuk satış maili taslağı
    Döndürür: {"intent": str, "email": str}
    """
    first    = person.get("First Name", "")
    last     = person.get("Last Name", "")
    title    = person.get("Title", "")
    company  = person.get("Company Name", "")
    industry = person.get("Industry", "")
    city     = person.get("City", "")
    country  = person.get("Country", "")
    email    = person.get("Email", "")
    employees = person.get("# Employees", "")

    prompt = f"""Sen deneyimli bir B2B satış uzmanısın.

Ürünümüz: {PRODUCT_DESCRIPTION}

Hedef kişi bilgileri:
- Ad Soyad : {first} {last}
- Unvan    : {title}
- Şirket   : {company}
- Sektör   : {industry}
- Konum    : {city}, {country}
- Çalışan  : {employees}
- E-posta  : {email}

İki görevin var:

1. SATIN ALMA NİYETİ (intent):
Bu şirketin neden ürünümüze ihtiyaç duyabileceğine dair gerçekçi, inandırıcı, spesifik ve tek cümlelik bir "Sentetik Satın Alma Niyeti" yaz. Sektöre ve şirkete özgü olsun, genel kalıplardan kaçın.

2. SOĞUK SATIŞ MAİLİ (email_draft):
Bu niyet verisini de kullanarak {first}'e özel, ikna edici, profesyonel ve kısa (3-4 paragraf) bir İngilizce soğuk satış maili yaz. Konu satırını (Subject:) en üste ekle. Şirket adını ve unvanını doğal şekilde kullan. Maili "Best regards,\\nLead The Way Team" ile bitir.

Yanıtını YALNIZCA aşağıdaki JSON formatında ver, başka hiçbir şey ekleme:
{{
  "intent": "...",
  "email_draft": "Subject: ...\\n\\n..."
}}"""

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    data = json.loads(raw)
    return {"intent": data.get("intent", ""), "email": data.get("email_draft", "")}

st.title("🎯 Lead The Way — AI B2B SDR")
st.caption("Doğal dilde yazın, Gemini Function Calling ile ilgili kişileri otomatik filtrelesin.")

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
        "- 1000'den fazla çalışanı olan teknoloji şirketlerindeki data scientist'lar\n"
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
)

display_cols = st.multiselect(
    "Gösterilecek Sütunlar",
    options=list(df_full.columns),
    default=["First Name", "Last Name", "Title", "Company Name", "Seniority",
             "Departments", "Industry", "City", "Country", "Email"],
    help="Sonuç tablosunda hangi sütunların görüneceğini seçin.",
)

if st.button("🚀 Filtrele", type="primary", disabled=not query):
    with st.spinner("Gemini Function Calling çalışıyor…"):
        try:
            system_prompt = build_system_prompt(df_full)
            response = gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"{system_prompt}\n\nKullanıcı sorgusu: {query}",
                config=types.GenerateContentConfig(
                    tools=[FILTER_DATAFRAME_TOOL],
                    tool_config=types.ToolConfig(
                        function_calling_config=types.FunctionCallingConfig(
                            mode="ANY",
                            allowed_function_names=["filter_dataframe"],
                        )
                    ),
                ),
            )
        except Exception as e:
            st.error(f"Gemini API hatası: {e}")
            st.stop()

    # Extract the function call from the response
    fc = None
    for part in response.candidates[0].content.parts:
        if part.function_call and part.function_call.name == "filter_dataframe":
            fc = part.function_call
            break

    if fc is None:
        st.error("Gemini, filter_dataframe fonksiyonunu çağırmadı. Sorgunuzu değiştirmeyi deneyin.")
        st.stop()

    # Parse function call arguments
    args = dict(fc.args)
    filters = [dict(f) for f in args.get("filters", [])]
    logic = args.get("logic", "AND")

    # Show the function call arguments for transparency
    with st.expander("🤖 Gemini'nin Ürettiği filter_dataframe Çağrısı", expanded=False):
        st.code(json.dumps({"filters": filters, "logic": logic}, ensure_ascii=False, indent=2), language="json")

    # Show parsed filters as a table
    if filters:
        st.subheader("📋 Uygulanan Filtreler")
        st.dataframe(pd.DataFrame(filters), use_container_width=True, hide_index=True)
        st.caption(f"Mantık: **{logic}**")

    # Execute filter_dataframe and persist result
    df_filtered = filter_dataframe(df_full, filters, logic)
    st.session_state["df_filtered"] = df_filtered
    st.session_state["show_cols"] = display_cols

# ── Results + Cold Outreach ───────────────────────────────────────────────────
if "df_filtered" in st.session_state:
    df_filtered = st.session_state["df_filtered"]
    show_cols_saved = st.session_state.get("show_cols", display_cols)

    st.markdown("---")
    st.subheader(f"✅ Sonuçlar — {len(df_filtered)} kişi bulundu")

    if df_filtered.empty:
        st.warning("Arama kriterlerine uyan kayıt bulunamadı. Sorgunuzu genişletmeyi deneyin.")
    else:
        show_cols = [c for c in show_cols_saved if c in df_filtered.columns] or list(df_filtered.columns)
        st.dataframe(df_filtered[show_cols].reset_index(drop=True), use_container_width=True)

        csv_out = df_filtered.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="⬇️ Sonuçları CSV olarak indir",
            data=csv_out,
            file_name="filtered_leads.csv",
            mime="text/csv",
        )

        # ── Cold Outreach Generator ───────────────────────────────────────────
        st.markdown("---")
        st.subheader("✉️ Kişiye Özel Soğuk Mail Taslağı")

        # Build display labels for the selectbox
        def make_label(row):
            name = f"{row.get('First Name', '')} {row.get('Last Name', '')}".strip()
            company = row.get("Company Name", "")
            title = row.get("Title", "")
            parts = [p for p in [name, title, company] if p]
            return " · ".join(parts) if parts else f"Satır {row.name}"

        labels = [make_label(df_filtered.iloc[i]) for i in range(len(df_filtered))]
        selected_label = st.selectbox(
            "Kişi seçin",
            options=labels,
            help="Mail taslağı oluşturulacak kişiyi seçin.",
        )
        selected_idx = labels.index(selected_label)
        selected_person = df_filtered.iloc[selected_idx].to_dict()

        if st.button("🪄 Intent + Mail Taslağı Oluştur", type="primary"):
            with st.spinner(f"Gemini, {selected_label} için içerik oluşturuyor…"):
                try:
                    result = generate_outreach(gemini_client, selected_person)
                    st.session_state["outreach_result"] = result
                    st.session_state["outreach_person"] = selected_label
                except Exception as e:
                    st.error(f"Mail taslağı oluşturulamadı: {e}")

        if "outreach_result" in st.session_state:
            result = st.session_state["outreach_result"]
            person_label = st.session_state.get("outreach_person", "")

            with st.expander(f"📬 {person_label} için Üretilen İçerik", expanded=True):
                st.markdown("#### 🎯 Sentetik Satın Alma Niyeti")
                st.info(result["intent"])

                st.markdown("#### 📧 Soğuk Satış Maili Taslağı")
                # Split subject line for highlighted display
                email_text = result["email"]
                if email_text.startswith("Subject:"):
                    lines = email_text.split("\n", 1)
                    subject_line = lines[0]
                    body = lines[1].strip() if len(lines) > 1 else ""
                    st.markdown(f"**{subject_line}**")
                    st.markdown("---")
                    st.markdown(body)
                else:
                    st.markdown(email_text)

                st.download_button(
                    label="⬇️ Maili .txt olarak indir",
                    data=result["email"].encode("utf-8"),
                    file_name=f"outreach_{selected_idx}.txt",
                    mime="text/plain",
                )

# ── Footer: raw data preview ──────────────────────────────────────────────────
with st.expander("📂 Ham Veri Önizlemesi (ilk 5 satır)", expanded=False):
    st.dataframe(df_full.head(), use_container_width=True)
