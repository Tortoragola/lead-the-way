# Plan: Lead The Way — Senior Engineer Insights → Roadmap

**TL;DR** — Current `app.py` is a working ~430 LOC single-file Streamlit MVP using Gemini Function Calling on a CSV. Senior engineer's three documents push us toward a production-grade architecture: (1) modularize the codebase, (2) replace synthetic intent with grounded real intent + scoring (1–10, DÜŞÜK/ORTA/YÜKSEK), (3) move from CSV→PostgreSQL (with JSONB intent layer), (4) expand the Function Calling toolset into a deterministic agent, (5) add Pydantic structured outputs, and (6) lay a security/compliance baseline (PII masking, guardrails, KVKK). LangGraph multi-agent and read-only replica are advanced phases — not MVP.

## Phases — Detailed File-by-File

### Phase 1 — Refactor & Hardening
**Goal**: Same UX, modular code, type-safe LLM outputs. No new features.

**New package layout**
```
app.py                          # UI shell only (~120 LOC target)
ltw/
  __init__.py
  config.py                     # Settings (Pydantic BaseSettings): API keys, DB URL, model names
  data.py                       # CSV loaders (current), schema introspection, sample_values
  filters.py                    # OPERATORS dict, filter_dataframe, column validation
  state.py                      # Typed wrappers around st.session_state keys
  models.py                     # All Pydantic schemas (FilterRule, FilterRequest, OutreachResult, CompanyIntentProfile)
  llm/
    __init__.py
    client.py                   # get_client() factory; model constants (FLASH=gemini-3-flash, LITE=gemini-3.1-flash-lite). No Pro.
    tools.py                    # FunctionDeclaration registry, built from Pydantic via types.Schema
    prompts.py                  # System prompts, build_system_prompt()
    filtering.py                # Wraps Gemini filter_dataframe call
    outreach.py                 # Intent + email generation, Pydantic-validated
```

**Steps**
1. Create `ltw/` package + `__init__.py` files.
2. Move `OPERATORS`, `filter_dataframe` → `ltw/filters.py`. Add `validate_columns(df, filters) -> list[FilterRule]` that returns only valid rules and raises on unknown columns (currently just warns).
3. Move `load_default_csv`, `sample_values`, `build_system_prompt` → `ltw/data.py` and `ltw/llm/prompts.py`.
4. Move `FILTER_DATAFRAME_TOOL` → `ltw/llm/tools.py`. Keep as-is for now; Phase 4 will Pydantic-ize.
5. Move `generate_outreach` → `ltw/llm/outreach.py`. Use `model=MODEL_REASONING` (`gemini-3-flash`). Replace manual `json.loads` with:
   - Define `OutreachResult(BaseModel)` in `ltw/models.py` with `intent: str`, `email_draft: str`.
   - Call Gemini with `response_schema=OutreachResult` (google-genai supports Pydantic directly) → parse via `response.parsed`.
6. **Hotfix during refactor**: current `app.py` uses `gemini-2.5-pro` in two places — both must be switched. Outreach call → `gemini-3-flash`; filter call → `gemini-3.1-flash-lite` (function-call arg extraction only). Pro is unavailable on free tier.
7. Wrap LLM calls in `@st.cache_data(ttl=3600)` keyed by `(model, prompt_hash, person_id)`. Use `hashlib.sha256(prompt).hexdigest()[:16]` as key.
8. `app.py` becomes a thin orchestrator that imports from `ltw` and renders UI only.
9. Add `pyproject.toml` (or update `requirements.txt`) with: `pydantic>=2`, `pydantic-settings`.

**Files touched**: [app.py](app.py) (gutted), [requirements.txt](requirements.txt).
**Files created**: 10 files under `ltw/`.

---

### Phase 2 — Real Intent Layer (Google Search Grounding)
**Goal**: Replace single-cell synthetic intent with audited, scored, source-cited real intent.

**Steps**
1. In `ltw/models.py` add (copy from insights doc):
   - `IntentLevel(str, Enum)` → HIGH/MEDIUM/LOW with Turkish values per doc.
   - `IntentSignal(BaseModel)` → `text: str, category: Literal['news','hiring','funding','tech','expansion'], weight: int (1-10)`.
   - `CompanyIntentProfile(BaseModel)` → exact fields from doc (unique_id, company_name, intent_score 1-10, intent_level, intent_signals: list[str], grounding_urls: list[str], last_intent_update: datetime).
2. In `ltw/llm/tools.py` declare new tool `enrich_company_intent` with params: `unique_id, company_name, website, country`.
3. In `ltw/llm/intent.py` (NEW):
   - `enrich_intent(client, company) -> CompanyIntentProfile`
   - Uses **`gemini-3-flash`** with `tools=[types.Tool(google_search=types.GoogleSearch())]` (Pro unavailable on free tier; Lite typically lacks Search Grounding).
   - Prompt: "Find recent (≤90 days) signals for {company} that suggest buying intent for {PRODUCT_DESCRIPTION}. Return signals + score per matrix: 1-4 generic news, 5-7 hiring/expansion, 8-10 funding/major tech change."
   - Parse `grounding_metadata.grounding_chunks[].web.uri` into `grounding_urls`.
   - `response_schema=CompanyIntentProfile` for structured output.
4. UI changes in `app.py`:
   - When a person is selected, add **"🔍 Niyet Analizi Yap"** button beside the existing outreach button.
   - Render result: colored score badge (green ≥8, yellow 5-7, gray ≤4), bullet list of `intent_signals`, expander with clickable `grounding_urls`.
   - Store profile in `st.session_state[f"intent:{unique_id}"]` (cache by company, not person — multiple contacts share company intent).
5. Feed intent into outreach: extend `generate_outreach` to accept an optional `CompanyIntentProfile` and inject its signals into the email prompt. This replaces today's invented intent sentence with real ones.
6. **Free-tier cost guard** (critical): skip the Flash+Grounding call if `last_intent_update < 24h` ago. Cache by `unique_id` at the company level (multiple contacts share one company profile). Persist to `st.session_state` in Phase 2; to Postgres `target_companies.last_intent_update` in Phase 3.

**Files touched**: [app.py](app.py), `ltw/models.py`, `ltw/llm/tools.py`, `ltw/llm/outreach.py`.
**Files created**: `ltw/llm/intent.py`.

---

### Phase 3 — PostgreSQL + Semantic Layer
**Goal**: Move from CSV-in-memory to PostgreSQL with a zero-trust access pattern and pre-defined safe query functions.

**Infrastructure**
1. `docker-compose.yml` (NEW) — single-node Postgres 16 with two roles:
   - `ltw_writer` (used by ETL only)
   - `ltw_agent` (read-only role, `GRANT SELECT` only; this is what Gemini-driven code uses)
2. `.env.example` (NEW) — `DATABASE_URL`, `DATABASE_URL_RO`, `GEMINI_API_KEY`.

**Schema** (`scripts/schema.sql`, NEW) — exact DDL from insights doc, with JSONB:
```
target_companies(unique_id PK, company_name, website, country, city, industry_code,
  employees_total, sales_volume_dollars, ceo_name, contact_email,
  intent_score, intent_level, intent_signals JSONB, grounding_urls JSONB, last_intent_update)
people(person_id PK, unique_id FK, first_name, last_name, title, email,
  seniority, department, technologies JSONB, keywords JSONB, opt_out BOOL DEFAULT false)
```

**ETL** (`scripts/csv_to_postgres.py`, NEW)
- Reads Bones firmographic CSV → `target_companies` (writer role).
- Reads Bones people CSV → `people` (join on CompanyName → unique_id).
- Idempotent: `INSERT … ON CONFLICT (unique_id) DO UPDATE`.
- Run with: `python scripts/csv_to_postgres.py`.

**Data access layer** (`ltw/db.py`, NEW)
- `get_engine_ro()` returns SQLAlchemy engine for `ltw_agent` role (used by agent tools).
- `get_engine_rw()` returns engine for ETL/intent-writer paths only.
- All agent paths import only `get_engine_ro()`.

**Semantic Layer** (`ltw/llm/semantic.py`, NEW) — pre-defined safe queries as Function-Calling tools:
- `get_companies_by_sector(sector: str, country: str|None, intent_level: IntentLevel|None, limit: int=50)`
- `get_high_intent_leads(min_score: int=8, country: str|None, limit: int=20)`
- `get_contacts_for_company(unique_id: str, seniority: str|None=None)`
- `search_companies(query: str)` — falls back to ILIKE on name/keywords (still no raw SQL from LLM).
- Each function uses parameterized SQLAlchemy queries; LLM never composes SQL strings.

**Integration**
- Existing `filter_dataframe` tool stays for the CSV upload path (back-compat).
- When DB mode is detected (env var present), `app.py` switches to semantic-layer tools and runs them via the same function-calling loop.

**Verification additions**
- Connect as `ltw_agent` and attempt `DELETE FROM target_companies` → must raise insufficient_privilege.
- Compare `SELECT COUNT(*)` to CSV row count post-ETL.

**Files touched**: [app.py](app.py), [requirements.txt](requirements.txt) (`sqlalchemy>=2`, `psycopg[binary]>=3`, `python-dotenv`).
**Files created**: `docker-compose.yml`, `.env.example`, `scripts/schema.sql`, `scripts/csv_to_postgres.py`, `ltw/db.py`, `ltw/llm/semantic.py`.

---

### Phase 4 — Multi-step Agent (sequential + parallel)
**Goal**: Single natural-language query chains multiple tools deterministically.

**Steps**
1. Refactor `app.py` query handler into a loop:
   ```
   while response has function_calls:
     for fc in parallel_function_calls: execute → collect FunctionResponse
     send all FunctionResponses back in one turn
   ```
2. Register all tools (`get_companies_by_sector`, `get_high_intent_leads`, `get_contacts_for_company`, `enrich_company_intent`, `generate_outreach_draft`) in one `types.Tool` block.
3. **Model routing inside the loop**: orchestration / reasoning turns run on `gemini-3-flash`; pure argument-fill turns (no new reasoning needed) can fall back to `gemini-3.1-flash-lite` to preserve daily Flash quota. The agent_loop decides per-turn based on whether `function_response` was just delivered (Lite) vs. fresh user query / chain end (Flash).
4. Set `function_calling_config(mode="ANY")` globally so the model never drops into chit-chat mid-chain.
5. Implement **thought signatures** preservation: when Gemini returns a function call with `thought_signature`, echo it back in the FunctionResponse so multi-step reasoning chains aren't broken.
6. Surface the full call graph in the existing transparency expander (list of tool calls + args + truncated results).
7. Add per-tool timeout (10s) and per-turn max iterations (6) as safety bounds.
8. **Batch confirmation**: if the chain is about to draft ≥5 outreach emails, pause and ask UI confirmation — protects both Flash RPD and user intent.

**Files touched**: [app.py](app.py), `ltw/llm/tools.py`, plus new `ltw/llm/agent_loop.py` for the orchestration logic.

---

### Phase 5 — Security & Compliance
**Goal**: KVKK/ETK-defensible posture before any real outreach.

**Steps**
1. `ltw/security/pii.py` (NEW) — Presidio wrapper:
   - `mask(text) -> (masked_text, mapping)` replaces emails/persons/phones with placeholders.
   - `rehydrate(text, mapping) -> text` restores after LLM response.
   - Applied around outreach generation (intent prompts don't carry PII).
2. `ltw/security/guardrails.py` (NEW) — LLM Guard pipeline on user query *before* it reaches Gemini: prompt-injection scanner, ban-substrings scanner.
3. Add `opt_out` filter to all semantic-layer queries (auto-`WHERE opt_out = false`).
4. README section: KVKK, ETK, retention policy, audit log location.
5. Audit log: append-only file or new `agent_audit` table (writer role) recording `(timestamp, user, tool_called, args, result_count)`.

**Files touched**: [README.md](README.md), [requirements.txt](requirements.txt) (`presidio-analyzer`, `presidio-anonymizer`, `llm-guard`), `ltw/llm/semantic.py` (opt_out filter), `ltw/llm/outreach.py` (mask/rehydrate).
**Files created**: `ltw/security/pii.py`, `ltw/security/guardrails.py`.

---

## Steps (parallelism guidance)
- Phase 1 steps 1–4: largely sequential (1 enables 2–4).
- Phase 2 steps 1–2 must follow Phase 1; steps 3–5 *parallelizable* within Phase 2.
- Phase 3 *can start in parallel* with Phase 2 (different files: data vs. llm).
- Phases 4–5 depend on Phase 3 (DB) and Phase 2 (intent model) being done.

## Relevant files
- [app.py](app.py) — to be split; keep as UI entry point. `generate_outreach` (lines ~150–210) needs Pydantic conversion; `FILTER_DATAFRAME_TOOL` (lines ~46–105) becomes one of many tools.
- [requirements.txt](requirements.txt) — add `pydantic>=2`, `presidio-analyzer`, `presidio-anonymizer`, `llm-guard` (Phase 5), `sqlalchemy` (Phase 3).
- [Bones - Firmographic Data Sample - Sample_Records.csv](Bones%20-%20Firmographic%20Data%20Sample%20-%20Sample_Records.csv) — source for Phase 3 ETL (UniqueID, CompanyName, Website, CEOName, Country, etc.).
- [Bones - People Inside Businesses Data Sample.csv](Bones%20-%20People%20Inside%20Businesses%20Data%20Sample.csv) — current default dataset; joins to firmographics via CompanyName in Phase 3.
- [insights/AI SDR İçin Veri Şeması ve Niyet Analizi Yapılandırması.md](insights/AI%20SDR%20%C4%B0%C3%A7in%20Veri%20%C5%9Eemas%C4%B1%20ve%20Niyet%20Analizi%20Yap%C4%B1land%C4%B1rmas%C4%B1.md) — exact SQL DDL + Pydantic schemas to copy for Phase 2/3.
- [insights/Gemini ve Function Calling ile Deterministik Yazılım Mimarisi.md](insights/Gemini%20ve%20Function%20Calling%20ile%20Deterministik%20Yaz%C4%B1l%C4%B1m%20Mimarisi.md) — sequential/parallel calling pattern for Phase 4.
- [insights/B2B Satış Otomasyonu ve Yapay Zeka SDR Mimari Rehberi.md](insights/B2B%20Sat%C4%B1%C5%9F%20Otomasyonu%20ve%20Yapay%20Zeka%20SDR%20Mimari%20Rehberi.md) — overall architecture + security guidance for Phase 5.

## Verification
1. Phase 1: `streamlit run app.py` still produces identical results for the 5 example queries in README; no regression in `filter_dataframe` output.
2. Phase 2: Pick 3 known companies; run intent enrichment; manually verify `grounding_urls` actually contain the claimed signals (anti-hallucination audit).
3. Phase 3: SQL query `SELECT COUNT(*) FROM target_companies` matches CSV row count; attempt `DELETE FROM target_companies` via the agent connection — must fail.
4. Phase 4: Single query "Find high-intent fintech CTOs in NY and draft emails" triggers ≥3 function calls in one turn (verifiable in the existing transparency expander).
5. Phase 5: Send a payload containing a real email through the masking layer; assert the raw email never appears in the Gemini request body (log inspection).

## Decisions (locked with user)
- **DB target = PostgreSQL** (with JSONB, dual-role read/write + read-only).
- **PII masking deferred to Phase 5**.
- **LangGraph deferred** (native Gemini sequential/parallel calling first).
- **Model routing (free-tier constrained)**:
  - `gemini-3.1-flash-lite` → function-call argument extraction (filter parsing, semantic-layer tool args, mid-chain arg-fill turns).
  - `gemini-3-flash` → outreach writing, intent reasoning with Google Search Grounding, multi-step orchestration.
  - **No Pro tier** — unavailable on Gemini free tier. Promote to Pro only when paid billing is enabled.
- **Free-tier survival rules**: 24h company-level intent cache; batch confirmation at ≥5 outreach drafts; per-turn iteration cap = 6.

## Free-tier capacity (rough)
- Lite RPD is generous; Flash is the bottleneck (~250 RPD typical).
- Typical session = 1 Lite filter + ~10 Flash (5 contacts × intent+email) ≈ 11 calls, of which ~10 hit Flash.
- Expected ceiling: **~20–25 sessions/day** before Flash RPD exhaustion; 24h intent cache lifts this 2–3× for repeat companies.
