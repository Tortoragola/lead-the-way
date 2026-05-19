# Lead The Way — AI B2B SDR Platform

Doğal dil komutlarıyla 5.000+ kişilik B2B iletişim veritabanını filtreleyen ve seçilen kişilere Gemini AI ile kişiselleştirilmiş soğuk satış maili taslakları oluşturan AI-native satış zekası platformu.

Veriler Supabase'de barındırılır. Uygulama sıfır konfigürasyonla çalışır — API anahtarı girmek veya CSV yüklemek gerekmez.

---

## Özellikler

- **Doğal Dil Filtreleme** — "İstanbul'daki fintech şirketlerinin pazarlama müdürlerini bul" gibi Türkçe/İngilizce komutlarla veritabanını anlık sorgula.
- **Gemini Function Calling** — Sorguyu tip-güvenli araç çağrılarına dönüştürür; 4 katmanlı filtre kalite sistemi ile yüksek geri çağırma oranı sağlar.
- **4-Katman Filtre Kalite Sistemi** — Sistem istemi kuralları + araç tanımlaması yönergesi + `normalize_filters()` post-processing + agent dispatch katmanı; Gemini'nin yanlış `equals` üretmesini ve Title/Departments çakışmasını önler.
- **Satın Alma Niyeti Zenginleştirme** — Google Search Grounding ile şirkete özgü gerçek niyet sinyalleri toplar, 1-10 arası skor üretir; 24 saatlik önbellek ile tekrar çağrıyı önler.
- **Soğuk Satış Maili Taslağı** — Niyet verisini maile entegre eden kişiye özel İngilizce outreach mesajı oluşturur.
- **Çok Adımlı Ajan Döngüsü** — `MAX_TURNS=12` ile ardışık tool çağrılarını yönetir; toplu e-posta taleplerinde kullanıcı onayı ister.
- **Aksiyon Kartları** — Ajan, sorgunu anladıktan sonra seçilebilir eylem önerileri sunar (ör. "Mail taslağı oluştur", "Niyet skoru ekle"); seçili eylemler tek tıkla uygulanır.
- **Kişi Listesi Tablosu** — Bulunan kişiler sohbet akışı içinde interaktif tablo olarak gösterilir; tek tıkla CSV indir.
- **API Retry / Resume** — Gemini "high demand" hatasında 3 otomatik deneme (5→15→30 s backoff); hâlâ başarısız olursa kullanıcıya "Tekrar Dene" butonu sunulur — ilerleme kaydedilir, sorgu baştan başlamaz.
- **Prompt Injection Koruması** — Her kullanıcı girdisi 3 katmanlı güvenlik taramasından geçer.
- **Denetim Günlüğü** — Her ajan çalışması Supabase `audit_log` tablosuna kaydedilir.

---

## Proje Yapısı

```
Lead The Way/
├── app.py                          # Streamlit chat arayüzü (tek sayfa, chat-first)
├── requirements.txt
├── .env.example                    # Ortam değişkeni şablonu
├── docker-compose.yml              # Yerel geliştirme için opsiyonel (PostgreSQL)
│
├── ltw/                            # Temel Python paketi
│   ├── config.py                   # Pydantic Settings (.env okuma)
│   ├── data.py                     # Supabase'den DataFrame yükleme
│   ├── db.py                       # Supabase istemcisi + SQLAlchemy engine + audit log
│   ├── filters.py                  # Filtreleme primitifleri + normalize_filters()
│   ├── models.py                   # CompanyIntentProfile, OutreachResult veri modelleri
│   ├── state.py                    # Streamlit session state yönetimi
│   ├── security/
│   │   ├── __init__.py             # check_prompt_injection() — regex tabanlı tarama
│   │   └── guardrails.py           # run_guardrails() — ban-substrings + opsiyonel LLM Guard
│   └── llm/
│       ├── agent_loop.py           # Çok adımlı ajan döngüsü (MAX_TURNS=12, retry mantığı)
│       ├── client.py               # Gemini istemci fabrikası + model sabitleri
│       ├── filtering.py            # Tek adımlı filtre çağrısı (CSV modu)
│       ├── intent.py               # Niyet zenginleştirme (Search Grounding)
│       ├── outreach.py             # Soğuk satış maili üretimi
│       ├── prompts.py              # Sistem istemleri (filtre strateji kuralları dahil)
│       ├── semantic.py             # DB modu parametrik SQL araçları
│       └── tools.py                # Gemini function-calling araç tanımlamaları
│
├── scripts/
│   ├── schema.sql                  # Supabase tablo şemaları
│   ├── roles.sql                   # PostgreSQL rol tanımları
│   ├── migrate_to_supabase.py      # CSV → Supabase tek seferlik migrasyon (5.000 kayıt)
│   └── csv_to_postgres.py          # CSV → yerel PostgreSQL yükleyici
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
DATABASE_URL=postgresql+psycopg://user:pass@host:port/db  # opsiyonel — semantic katman için
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

Uygulama tek sayfalık bir sohbet arayüzüdür. Türkçe veya İngilizce sorgu yaz; ajan araçları arka planda çalıştırır.

### Örnek sorgular

```
İstanbul'daki fintech şirketlerinin pazarlama müdürlerini bul
```
```
Bankacılık sektöründeki kıdemli veri bilimciler için mail taslağı oluştur
```
```
Yüksek niyet skorlu SaaS şirketleri hangileri?
```
```
Tüm Almanya'daki CTO'lara outreach kampanyası başlat
```

### Akış

1. **Sorgu** — Kullanıcı doğal dil ile istek yazar.
2. **Filtre + Kişi Listesi** — Ajan `search_people` veya `filter_dataframe` araçlarını çağırır; bulunan kişiler tabloda gösterilir ve CSV olarak indirilebilir.
3. **Aksiyon Kartı** _(opsiyonel)_ — Ajan birden fazla adım içeren sorguları "Şimdi ne yapalım?" aksiyon kartıyla sunar. Onay kutucuklarından seçim yapılır ve **Uygula** butonuna basılır.
4. **Niyet Zenginleştirme** — Ajan `enrich_company_intent` ile şirkete özel satın alma sinyallerini çeker (Google Search Grounding).
5. **Outreach Taslağı** — Seçilen kişi için kişiselleştirilmiş İngilizce mail taslağı oluşturulur.
6. **Toplu Onay** — 5+ kişi için taslak talebi geldiğinde sistem durur ve kullanıcı onayı ister.
7. **API Retry** — Gemini "high demand" hatasında otomatik yeniden deneme; son çare olarak "🔄 Tekrar Dene" butonu gösterilir.

---

## Teknoloji Yığını

| Katman | Araç |
|---|---|
| Arayüz | [Streamlit](https://streamlit.io) ≥ 1.35 |
| AI Akıl Yürütme | `gemini-3-flash-preview` — çok adımlı ajan, orchestration |
| AI Çıkarım | `gemini-3.1-flash-lite` — hızlı argüman doldurma, extraction |
| AI Grounding | `gemini-2.5-flash` — Google Search Grounding (Gemini 3 desteklemiyor) |
| AI SDK | `google-genai` ≥ 0.8 — Function Calling, JSON modu, Search Grounding |
| Veritabanı | [Supabase](https://supabase.com) (PostgreSQL) + `supabase-py` ≥ 2.0 |
| Semantic Katman | SQLAlchemy — tamamen parametrik sorgular, LLM asla SQL yazmaz |
| Yapılandırma | `pydantic-settings` ≥ 2 — `.env` okuma |
| Veri İşleme | `pandas` ≥ 2.0 |

---

## Mimari: 4-Katman Filtre Kalite Sistemi

Gemini'nin Title/Departments gibi serbest metin sütunları için yanlış `equals` operatörü seçmesini önlemek amacıyla dört bağımsız katman uygulanmaktadır:

| # | Katman | Dosya | Açıklama |
|---|---|---|---|
| 1 | Sistem İstemi | `ltw/llm/prompts.py` | `filter_dataframe` çağrısından önce modele 4 kural verilir |
| 2 | Araç Tanımlaması | `ltw/llm/tools.py` | `operator` parametre açıklamalarına kural eklendi |
| 3 | `normalize_filters()` | `ltw/filters.py` | Modelin ürettiği `equals`'ı `contains`'e yükseltir; uyarı üretir |
| 4 | Dispatch Katmanı | `ltw/llm/agent_loop.py` | `normalize_filters` sonuçlarını `outcome.warnings`'a ekler |

---

## Mimari: API Retry / Resume Sistemi

Gemini API'si yoğun talep ("high demand", 429, 503) altında hata döndürdüğünde iki savunma hattı devreye girer:

| Aşama | Mekanizma | Dosya |
|---|---|---|
| 1 — Otomatik backoff | Aynı `generate_content` çağrısı 3 kez tekrarlanır: 5 s → 15 s → 30 s bekleme | `ltw/llm/agent_loop.py` — `_is_retriable_error()`, `_RETRY_DELAYS` |
| 2 — Kullanıcı resume | Hâlâ başarısız olursa `retriable=True` döner; `app.py` sorguyu + geçmişi `pending_retry`'da saklar; kullanıcı "🔄 Tekrar Dene" butonuna basarak kaldığı yerden devam eder | `app.py` — `_render_retry_button()`, `_record_result()` |

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
| 3. LLM Guard (optional) | `ltw/security/guardrails.py` | ~50–200 ms | ML-based `PromptInjectionV2` scanner from Protect AI — active if `pip install llm-guard` |

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
