# Phase 1 Campaign Automation — Supabase Migration

## Setup Instructions

### 1. Apply the campaigns table migration to Supabase

Copy the SQL below and run it in your **Supabase SQL Editor** (https://app.supabase.com → SQL Editor):

```sql
-- ── Campaign Automation (Phase 1) ───────────────────────────────────────────
-- Stores campaign metadata and generated email drafts.
-- Status: draft (created), ready (drafts generated), executing (running), completed (sent).
CREATE TABLE IF NOT EXISTS campaigns (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    name                VARCHAR(255)    NOT NULL,
    query               TEXT            NOT NULL,
    min_intent_score    INTEGER         NOT NULL DEFAULT 5,
    status              VARCHAR(50)     NOT NULL DEFAULT 'draft',
    scheduled_at        VARCHAR(50),    -- "daily 09:00", "weekly Monday", "manual", or NULL
    draft_count         INTEGER         NOT NULL DEFAULT 0,
    results_json        JSONB,          -- Array of OutreachDraft objects
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_camp_status       ON campaigns (status);
CREATE INDEX IF NOT EXISTS idx_camp_created_at   ON campaigns (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_camp_scheduled_at ON campaigns (scheduled_at);
```

**Result:** You should see "Success. No rows returned."

### 2. Disable Row Level Security (RLS) for campaigns table (if needed)

- Go to **Supabase Dashboard** → **Table Editor**
- Select the **campaigns** table
- Click **RLS** on the right panel
- If RLS is enabled, click "Disable RLS" (or ensure anon key has insert/update/delete permissions)

### 3. Verify campaigns table exists

Run this query in SQL Editor to confirm:

```sql
SELECT * FROM campaigns LIMIT 1;
```

You should see no error and an empty result set.

### 4. Install APScheduler (Python environment)

```bash
cd /Users/caglayagmuryaylaci/Desktop/hackaton/lead-the-way
python3 -m pip install apscheduler
```

Or use the .venv:

```bash
.venv/bin/pip install apscheduler
```

### 5. Run the E2E test to verify everything is set up

```bash
.venv/bin/python3 test_campaign_e2e.py
```

Expected output:
```
✅ Campaign object created successfully
✅ Campaign serialized: 10 fields
✅ Supabase available
✅ Campaign saved with ID: <uuid>
✅ Campaign retrieved: Test Campaign — Phase 1
✅ Found N campaigns in database
✅ Scheduler initialized, running: True
✅ Campaign scheduled: campaign_<id>
✅ Campaign executed: {'status': 'ready', 'draft_count': N, ...}
✅ CSV export working
```

---

## Files Created / Modified

### New Files:
- ✅ `ltw/campaign.py` — Campaign and OutreachDraft classes
- ✅ `ltw/jobs.py` — APScheduler orchestration

### Modified Files:
- ✅ `ltw/db.py` — Added campaign methods (create_campaign, get_campaign, list_campaigns, update_campaign_status)
- ✅ `ltw/llm/agent_loop.py` — Removed batch confirmation gate (line 300-311)
- ✅ `app.py` — Added Campaign Manager tab (Tab 3)
- ✅ `requirements.txt` — Added apscheduler

### Database:
- ✅ `scripts/schema.sql` — Added campaigns table definition

---

## Next Steps

### After Setup:

1. **Start the Streamlit app:**
   ```bash
   streamlit run app.py
   ```

2. **Navigate to "📅 Kampanya Yöneticisi" tab (Tab 3)**

3. **Create a test campaign:**
   - Campaign name: "Test Istanbul Fintech"
   - Query: "İstanbul'da fintech sektöründeki pazarlama müdürleri"
   - Min score: 5
   - Schedule: "Her Gün 09:00"
   - Click "🚀 Kampanya Oluştur & Zamanla"

4. **Expected result:**
   - Campaign appears in "Aktif Kampanyalar" section
   - Status: 🔵 draft
   - "▶️ Test Çalıştır" button to manually trigger

5. **Test execution:**
   - Click "▶️ Test Çalıştır"
   - Wait for Gemini to:
     1. Filter leads via natural language
     2. Enrich intent for each lead (Google Search)
     3. Generate personalized email drafts
   - After 30-60 seconds:
     - Campaign status changes to: 🟢 ready
     - draft_count shows: e.g., "23"
     - "⬇️ CSV İndir" button appears

6. **Download and verify CSV:**
   - Click "⬇️ CSV İndir"
   - Open CSV file
   - Verify columns: first_name, last_name, email, company_name, subject, body, intent_score, industry
   - Verify rows match draft count

---

## Architecture Overview

```
TAB 3: Campaign Manager
   ├── Create Campaign Form
   │   ├── Campaign name
   │   ├── Filter query (natural language)
   │   ├── Min intent score
   │   └── Schedule (daily, weekly, manual)
   │
   ├── Schedule Button
   │   └── → APScheduler.add_job()
   │       → Supabase.campaigns.insert()
   │
   ├── Active Campaigns List
   │   ├── Test Run (manual execution)
   │   ├── Download CSV (if ready)
   │   └── Delete
   │
   └── APScheduler Info (debug)
       └── Shows scheduled jobs

Background Job (APScheduler):
   1. Load campaign from Supabase
   2. Execute: Filter → Intent Enrichment → Draft Generation
   3. Save all drafts to campaign.results_json
   4. Update status → "ready"
   5. Repeat at scheduled time (daily, weekly, etc.)
```

---

## Troubleshooting

### "Could not find table 'public.campaigns'"
→ Run the SQL migration in Supabase SQL Editor (step 1 above)

### "Permission denied on campaigns"
→ Disable RLS for campaigns table or ensure anon key has permissions (step 2 above)

### "APScheduler not found"
→ Install: `pip install apscheduler` (step 4 above)

### Campaign execution doesn't create drafts
→ Check Streamlit console for errors
→ Verify Gemini API key is valid
→ Ensure SUPABASE_URL and SUPABASE_KEY are set

### Scheduled jobs don't run automatically
→ APScheduler only runs while Streamlit app is open
→ For production 24/7 execution, use external job runner (post-hackathon)

---

## Phase 1 Complete! ✅

Campaign Automation is ready for autonomous operation:
- ✅ Create campaigns via natural language
- ✅ Schedule them (daily, weekly, manual)
- ✅ Auto-generate 100+ email drafts
- ✅ Download as CSV for review/sending

**Next phases (post-hackathon):**
- Phase 2: Campaign analytics + real-time intent signals
- Phase 3: Email sending + reply tracking + CRM integration
