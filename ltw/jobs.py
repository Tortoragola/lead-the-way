"""APScheduler jobs for campaign automation."""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

ROOT = Path(__file__).resolve().parent.parent


def setup_scheduler():
    """Initialize and start background scheduler."""
    scheduler = BackgroundScheduler()
    if not scheduler.running:
        scheduler.start()
    return scheduler


def execute_campaign(campaign_id: str, gemini_client, df_full) -> dict:
    """
    Autonomous campaign execution: filter → intent enrichment → draft generation.

    Returns dict with:
    - draft_count: number of email drafts generated
    - status: "ready" if successful
    - error: error message if failed
    """
    from ltw.campaign import Campaign, OutreachDraft
    from ltw.llm.filtering import request_filters
    from ltw.llm.intent import enrich_intent
    from ltw.llm.outreach import generate_outreach
    from ltw.db import get_supabase_client

    try:
        # 1. Load campaign metadata from Supabase
        db = get_supabase_client()
        campaign_data = (
            db.table("campaigns")
            .select("*")
            .eq("id", campaign_id)
            .execute()
        )

        if not campaign_data.data:
            return {"status": "error", "error": f"Campaign {campaign_id} not found"}

        campaign = Campaign.from_dict(campaign_data.data[0])
        campaign.status = "executing"

        # Update status to executing
        db.table("campaigns").update({"status": "executing"}).eq("id", campaign_id).execute()

        # 2. Filter leads via natural language
        filter_call = request_filters(gemini_client, df_full, campaign.query)

        if not filter_call.called:
            return {"status": "error", "error": "Gemini filtering failed: function not called"}

        # Apply filters to DataFrame
        from ltw.filters import filter_dataframe
        filter_outcome = filter_dataframe(df_full, filter_call.filters, filter_call.logic)
        df_filtered = filter_outcome.df

        if df_filtered.empty:
            return {"status": "ready", "draft_count": 0, "campaign_name": campaign.name}

        draft_count = 0

        # 3. For each filtered lead: enrich intent and generate draft
        for _, person in df_filtered.iterrows():
            company_name = str(person.get("Company Name", "")).strip()
            if not company_name:
                continue

            # Enrich intent via Google Search Grounding
            try:
                intent = enrich_intent(
                    gemini_client,
                    unique_id=company_name.lower(),
                    company_name=company_name,
                    website=str(person.get("Website", "")).strip(),
                    country=str(person.get("Country", "")).strip(),
                )
            except Exception as e:
                print(f"⚠️ Intent enrichment failed for {company_name}: {e}")
                continue

            # Filter by min_intent_score
            if intent.intent_score < campaign.min_intent_score:
                continue

            # Generate email draft
            try:
                draft_result = generate_outreach(
                    gemini_client,
                    person=dict(person),
                    intent_profile=intent,
                )
            except Exception as e:
                print(f"⚠️ Draft generation failed for {person.get('First Name')} {person.get('Last Name')}: {e}")
                continue

            # Save to campaign
            draft = OutreachDraft(
                first_name=str(person.get("First Name", "")).strip(),
                last_name=str(person.get("Last Name", "")).strip(),
                email=str(person.get("Email", "")).strip(),
                company_name=company_name,
                subject=draft_result.subject if hasattr(draft_result, "subject") else "Your Subject Here",
                body=draft_result.body if hasattr(draft_result, "body") else "Draft body here",
                intent_score=intent.intent_score,
                industry=str(person.get("Industry", "")).strip(),
            )
            campaign.save_draft(draft)
            draft_count += 1

        # 4. Save campaign to Supabase
        campaign.status = "ready"
        campaign_dict = campaign.to_dict()

        db.table("campaigns").update({
            "status": "ready",
            "draft_count": draft_count,
            "results_json": campaign_dict.get("results_json"),
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", campaign_id).execute()

        print(f"✅ Campaign {campaign.name}: {draft_count} drafts generated, status=ready")
        return {
            "status": "ready",
            "draft_count": draft_count,
            "campaign_name": campaign.name,
        }

    except Exception as e:
        print(f"❌ Campaign execution failed: {e}")
        db = get_supabase_client()
        db.table("campaigns").update({"status": "error"}).eq("id", campaign_id).execute()
        return {"status": "error", "error": str(e)}


def schedule_campaign(scheduler: BackgroundScheduler, campaign_id: str, schedule_cron: str) -> dict:
    """
    Schedule a campaign to run on cron schedule.

    Args:
        scheduler: BackgroundScheduler instance
        campaign_id: Campaign ID to schedule
        schedule_cron: Schedule expression:
            - "daily 09:00" → every day 9am
            - "weekly Monday" → every Monday 9am
            - "manual" → no automatic scheduling

    Returns:
        dict with status and job_id
    """
    if schedule_cron == "manual":
        return {"status": "manual", "message": f"Campaign {campaign_id} set to manual execution"}

    try:
        # Parse simple cron patterns
        if schedule_cron == "daily 09:00":
            trigger = CronTrigger(hour=9, minute=0)
        elif schedule_cron == "weekly Monday":
            trigger = CronTrigger(hour=9, minute=0, day_of_week=0)
        else:
            # Assume it's a proper cron expression
            trigger = CronTrigger.from_crontab(schedule_cron)

        job_id = f"campaign_{campaign_id}"

        # Import here to avoid circular imports
        from ltw.llm.client import get_client
        from ltw.config import get_settings
        from ltw.data import load_from_supabase

        gemini_client = get_client(get_settings().gemini_api_key)
        df_full = load_from_supabase()

        job = scheduler.add_job(
            execute_campaign,
            trigger=trigger,
            args=[campaign_id, gemini_client, df_full],
            id=job_id,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )

        print(f"✅ Campaign {campaign_id} scheduled: {trigger}")
        return {
            "status": "scheduled",
            "job_id": job.id,
            "next_run_time": str(job.next_run_time) if job.next_run_time else None,
        }
    except Exception as e:
        print(f"❌ Campaign scheduling failed: {e}")
        return {"status": "error", "error": str(e)}


def cancel_campaign(scheduler: BackgroundScheduler, campaign_id: str) -> dict:
    """Cancel scheduled campaign execution."""
    job_id = f"campaign_{campaign_id}"
    try:
        scheduler.remove_job(job_id)
        print(f"✅ Campaign {campaign_id} scheduling cancelled")
        return {"status": "cancelled"}
    except Exception as e:
        print(f"❌ Failed to cancel campaign: {e}")
        return {"status": "error", "error": str(e)}


# Global scheduler instance (initialized on app startup)
_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    """Get or create global scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = setup_scheduler()
    return _scheduler


def shutdown_scheduler():
    """Shutdown global scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
        _scheduler = None
