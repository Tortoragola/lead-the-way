# Lead The Way — AI B2B SDR Platform

Doğal dil komutlarıyla 5.000+ kişilik B2B iletişim veritabanını filtreleyen ve seçilen kişilere Gemini AI ile kişiselleştirilmiş soğuk satış maili taslakları oluşturan AI-native satış zekası platformu.

Veriler Supabase'de barındırılır. Uygulama sıfır konfigürasyonla çalışır — API anahtarı girmek veya CSV yüklemek gerekmez.

---

## Özellikler

- **Doğal Dil Filtreleme** — "İstanbul'daki fintech şirketlerinin pazarlama müdürlerini bul" gibi Türkçe/İngilizce komutlarla veritabanını anlık sorgula.
- **Gemini Function Calling** — Sorguyu tip-güvenli `filter_dataframe` çağrısına dönüştürür; 4 katmanlı filtre kalite sistemi ile yüksek geri çağırma oranı sağlar.
- **4-Katman Filtre Kalite Sistemi** — Sistem istemi kuralları + araç tanımlaması yönergesi + `normalize_filters()` post-processing + agent dispatch katmanı; Gemini'nin yanlış `equals` üretmesini ve Title/Departments çakışmasını önler.
- **Satın Alma Niyeti Zenginleştirme** — Google Search Grounding ile şirkete özgü gerçek niyet sinyalleri toplar, 1-10 arası skor üretir; 24 saatlik önbellek ile tekrar çağrıyı önler.
- **Soğuk Satış Maili Taslağı** — Niyet verisini maile entegre eden kişiye özel İngilizce outreach mesajı oluşturur.
- **Çok Adımlı Ajan Döngüsü** — `MAX_TURNS=6` ile ardışık tool çağrılarını yönetir; toplu e-posta taleplerinde kullanıcı onayı ister.
- **Prompt Injection Koruması** — Her kullanıcı girdisi güvenlik taramasından geçer.
- **Denetim Günlüğü** — Her ajan çalışması Supabase `audit_log` tablosuna kaydedilir.
- **CSV İndir** — Filtrelenmiş lead listesini ve mail taslağını dosyaya kaydet.

---

## Proje Yapısı

```
Lead The Way/
├── app.py                          # Ana Streamlit uygulaması (Tab 1: Filtre, Tab 2: Ajan)
├── requirements.txt
├── .env.example                    # Ortam değişkeni şablonu
├── docker-compose.yml              # Yerel geliştirme için opsiyonel
│
├── ltw/                            # Temel Python paketi
│   ├── config.py                   # Pydantic Settings (.env okuma)
│   ├── data.py                     # Supabase'den DataFrame yükleme
│   ├── db.py                       # Supabase istemcisi + denetim günlüğü
│   ├── filters.py                  # Filtreleme primitifleri + normalize_filters()
│   ├── models.py                   # CompanyIntentProfile, OutreachResult veri modelleri
│   ├── security.py                 # Prompt injection koruması
│   ├── state.py                    # Streamlit session state yönetimi
│   └── llm/
│       ├── agent_loop.py           # Çok adımlı ajan döngüsü (MAX_TURNS=6)
│       ├── client.py               # Gemini istemci fabrikası + model sabitleri
│       ├── filtering.py            # Tab 1 tek adımlı filtre çağrısı
│       ├── intent.py               # Niyet zenginleştirme (Search Grounding)
│       ├── outreach.py             # Soğuk satış maili üretimi
│       ├── prompts.py              # Sistem istemleri (filtre strateji kuralları dahil)
│       ├── semantic.py             # DB modu semantik araçlar
│       └── tools.py                # Gemini function-calling araç tanımlamaları
│
├── scripts/
│   ├── schema.sql                  # Supabase tablo şemaları
│   ├── migrate_to_supabase.py      # CSV → Supabase tek seferlik migrasyon (5.000 kayıt)
│   └── roles.sql                   # PostgreSQL rol tanımları
│
└── insights/                       # Mimari ve tasarım notları
```

---

## Kurulum

### Gereksinimler

- Python 3.10+
- [Gemini API Anahtarı](https://aistudio.google.com/app/apikey) (ücretsiz tier yeterli)
- Supabase hesabı (ücretsiz plan yeterli)

### 1. Depoyu klonla

```bash
git clone https://github.com/Tortoragola/lead-the-way.git
cd lead-the-way
```

### 2. Sanal ortam oluştur ve bağımlılıkları yükle

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Ortam değişkenlerini yapılandır

```bash
cp .env.example .env
```

`.env` dosyasını düzenle:

```env
GEMINI_API_KEY=your-gemini-api-key-here
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key
```

### 4. Supabase şemasını oluştur (ilk kez)

`scripts/schema.sql` içeriğini Supabase Dashboard → SQL Editor'da çalıştır.

### 5. Veriyi Supabase'e aktar (ilk kez)

```bash
python scripts/migrate_to_supabase.py
```

22 şirket ve 5.000 kişilik kayıt Supabase'e yüklenir.

### 6. Uygulamayı başlat

```bash
streamlit run app.py
```

Tarayıcı otomatik açılır → `http://localhost:8501`

---

## Kullanım

### Tab 1 — Manuel Filtrele

Sütun/operatör/değer seçerek veya doğal dil kutusuyla hızlı filtreleme:

- `Türkiye'deki pazarlama müdürlerini bul`
- `Bankacılık sektöründeki kıdemli veri bilimciler`
- `1000'den fazla çalışanı olan teknoloji şirketlerindeki CTO'lar`

Sonuç tablosundan bir kişi seçip **Intent + Mail Taslağı Oluştur** butonuna bas.

### Tab 2 — AI Ajan

Çok adımlı ajan döngüsü ile gelişmiş sorgular:

- `İstanbul fintech şirketlerindeki C-seviye yöneticileri bul ve ilk 3'ü için mail taslağı oluştur`
- `Yüksek niyet skorlu SaaS şirketleri hangileri?`
- `Tüm Almanya'daki CTO'lara outreach kampanyası başlat`

---

## Teknoloji Yığını

| Katman | Araç |
|---|---|
| Arayüz | [Streamlit](https://streamlit.io) ≥ 1.35 |
| AI Modeli | Google Gemini 3 Flash Preview (akıl yürütme) + Gemini 3.1 Flash Lite (çıkarım) |
| AI SDK | `google-genai` — Function Calling, JSON modu, Search Grounding |
| Veritabanı | [Supabase](https://supabase.com) (PostgreSQL) + `supabase-py` ≥ 2.0 |
| Yapılandırma | `pydantic-settings` ≥ 2 — `.env` okuma |
| Veri İşleme | `pandas` ≥ 2.0 |

---

## Mimari: 4-Katman Filtre Kalite Sistemi

Gemini'nin Title/Departments gibi serbest metin sütunları için yanlış `equals` operatörü seçmesini önlemek amacıyla dört bağımsız katman uygulanmaktadır:

| # | Katman | Dosya | Açıklama |
|---|---|---|---|
| 1 | Sistem İstemi | `ltw/llm/prompts.py` | `filter_dataframe` çağrısından önce modele 4 kural verilir |
| 2 | Araç Tanımlaması | `ltw/llm/tools.py` | `operator` ve `logic` parametre açıklamalarına kural eklendi |
| 3 | `normalize_filters()` | `ltw/filters.py` | Modelin ürettiği `equals`'ı `contains`'e yükseltir; uyarı üretir |
| 4 | Dispatch Katmanı | `ltw/llm/agent_loop.py` | `normalize_filters` sonuçlarını `outcome.warnings`'a ekler |

---

## Yapılandırma

`ltw/config.py` içindeki `PRODUCT_DESCRIPTION` sabitini kendi ürününüzle güncelleyin:

```python
PRODUCT_DESCRIPTION = (
    "Lead The Way: Şirketlerin doğal dil komutlarıyla B2B iletişim "
    "veritabanlarını anlık filtreleyip, yapay zeka destekli kişiselleştirilmiş "
    "soğuk satış mesajları oluşturmasını sağlayan AI-native satış zekası platformu."
)
```

---

## Security & Compliance

### Guardrails (OWASP LLM01 — Prompt Injection)

All user input passes through a three-layer pipeline before reaching Gemini:

| Layer | File | Speed | Description |
|---|---|---|---|
| 1. Ban-substrings | `ltw/security/guardrails.py` | < 0.1 ms | Blocks known harmful phrases (data-exfiltration attempts, jailbreak triggers) |
| 2. Regex injection scanner | `ltw/security/__init__.py` | < 1 ms | Heuristic patterns: instruction-override, SQL injection, system-prompt tags |
| 3. LLM Guard (optional) | `ltw/security/guardrails.py` | ~50-200 ms | ML-based `PromptInjectionV2` scanner from Protect AI — active if `pip install llm-guard` |

Any blocked query returns an error to the user and is recorded in `audit_log` with `injection_flagged=true`.

### Data Access

- The app only connects to Supabase using the **anon key** (row-level read access, no writes to sensitive tables).
- Every semantic-layer SQL query is **fully parameterized** — the LLM never composes SQL strings.
- `get_distinct_values` uses a hardcoded column **allowlist** before f-stringing the column name into the query.
- Every `people` table query includes `WHERE opt_out = FALSE` — opted-out contacts are never surfaced to the LLM or the user.

### Audit Log

Every agent run writes a row to the `audit_log` table in Supabase:

| Column | Description |
|---|---|
| `event_type` | `filter`, `outreach_draft` |
| `company_name` | Company queried (truncated at 255 chars) |
| `person_email` | **SHA-256 hash** of the email — never the raw address |
| `query_summary` | First 200 chars of the user query |
| `model_used` | `gemini-3-flash-preview` or `gemini-3.1-flash-lite` |
| `injection_flagged` | Boolean — true if the query was blocked by guardrails |

### KVKK / ETK (Turkish Data Protection)

- Contact data is used only for the purpose for which it was collected (B2B sales outreach).
- Raw email addresses are **never stored** in the audit log (hashed only).
- Opted-out contacts are filtered at the SQL level — they cannot be retrieved via any agent tool.
- Outreach emails are **drafts only** — no emails are sent by the platform.

### PII Masking — intentionally not implemented

Lead The Way's core value is surfacing contact information (names, emails, titles) to the sales user. Masking PII before sending to the LLM would break the product. The security boundary is the **access control layer** (anon key + row-level security) and the **opt_out filter**, not in-transit masking.

---

## Lisans

MIT
