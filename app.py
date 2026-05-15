"""Lead The Way — Streamlit UI shell.

All domain logic lives in the ``ltw`` package; this file only handles
rendering and routing user input to the package functions.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from ltw.config import get_settings
from ltw.data import load_default_csv, load_from_supabase
from ltw.db import db_available, get_supabase_client, create_campaign, list_campaigns, update_campaign_status
from ltw.campaign import Campaign, OutreachDraft
from ltw.filters import filter_dataframe
from ltw.llm.agent_loop import AgentRunResult, run_agent
from ltw.llm.client import get_client
from ltw.llm.filtering import request_filters
from ltw.llm.intent import enrich_intent
from ltw.llm.outreach import generate_outreach
from ltw.models import CompanyIntentProfile, IntentLevel
from ltw.security import check_prompt_injection
from ltw import state as S
from ltw.jobs import get_scheduler, schedule_campaign, execute_campaign


INTENT_CACHE_TTL = timedelta(hours=24)


def _intent_cache_key(company_name: str) -> str:
    return f"intent:{(company_name or '').strip().lower()}"


def _get_cached_intent(company_name: str) -> CompanyIntentProfile | None:
    profile = st.session_state.get(_intent_cache_key(company_name))
    if not isinstance(profile, CompanyIntentProfile):
        return None
    if datetime.utcnow() - profile.last_intent_update > INTENT_CACHE_TTL:
        return None
    return profile


def _set_cached_intent(profile: CompanyIntentProfile) -> None:
    st.session_state[_intent_cache_key(profile.company_name)] = profile


def _level_badge(level: IntentLevel, score: int) -> str:
    color = {"YÜKSEK": "#16a34a", "ORTA": "#ca8a04", "DÜŞÜK": "#6b7280"}[level.value]
    return (
        f"<span style='background:{color};color:white;padding:4px 12px;"
        f"border-radius:12px;font-weight:600;'>"
        f"{level.value} · {score}/10</span>"
    )


# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Lead The Way – AI B2B SDR",
    page_icon="🎯",
    layout="wide",
)


# ── Cached wrappers ─────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _load_default_csv_cached() -> pd.DataFrame:
    return load_default_csv()


@st.cache_data(show_spinner="Supabase'den veri yükleniyor…", ttl=600)
def _load_supabase_data_cached() -> pd.DataFrame:
    return load_from_supabase()


# ── UI ──────────────────────────────────────────────────────────────────────
st.title("🎯 Lead The Way — AI B2B SDR")
st.caption("Doğal dilde yazın, Gemini Function Calling ile ilgili kişileri otomatik filtrelesin.")

with st.sidebar:
    st.header("⚙️ Ayarlar")
    st.markdown(
        "**Örnek sorgular:**\n"
        "- Türkiye'deki pazarlama müdürlerini bul\n"
        "- İstanbul'da fintech sektöründeki C-level yöneticiler\n"
        "- 1000'den fazla çalışanı olan teknoloji şirketlerindeki data scientist'lar\n"
        "- Bankacılık sektöründeki kıdemli mühendisler\n"
        "- Microsoft teknolojisi kullanan şirketler"
    )

try:
    gemini_client = get_client(get_settings().gemini_api_key)
except Exception as e:
    st.error(f"API yapılandırma hatası: {e}")
    st.stop()

# Load data from Supabase
try:
    df_full = _load_supabase_data_cached()
except Exception as e:
    st.error(f"Supabase'den veri yüklenirken hata: {e}")
    st.stop()

col_a, col_b, col_c = st.columns(3)
col_a.metric("Toplam Kişi", len(df_full))
col_b.metric("Sütun Sayısı", len(df_full.columns))
col_c.metric("Ülke Sayısı", df_full["Country"].nunique() if "Country" in df_full.columns else "—")

st.markdown("---")

tab_filter, tab_agent, tab_campaign = st.tabs(["📊 Filtrele & Outreach", "🤖 AI Asistan (Çok Adımlı)", "📅 Kampanya Yöneticisi"])

# ═══════════════════════════════════════════════════════════════════════════
# TAB 1 — Filter + Outreach (existing UI)
# ═══════════════════════════════════════════════════════════════════════════
with tab_filter:

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
             call = request_filters(gemini_client, df_full, query)
         except Exception as e:
             st.error(f"Gemini API hatası: {e}")
             st.stop()

     if not call.called:
         st.error("Gemini, filter_dataframe fonksiyonunu çağırmadı. Sorgunuzu değiştirmeyi deneyin.")
         st.stop()

     with st.expander("🤖 Gemini'nin Ürettiği filter_dataframe Çağrısı", expanded=False):
         st.code(
             json.dumps({"filters": call.filters, "logic": call.logic}, ensure_ascii=False, indent=2),
             language="json",
         )

     if call.filters:
         st.subheader("📋 Uygulanan Filtreler")
         st.dataframe(pd.DataFrame(call.filters), use_container_width=True, hide_index=True)
         st.caption(f"Mantık: **{call.logic}**")

     outcome = filter_dataframe(df_full, call.filters, call.logic)
     for w in outcome.warnings:
         st.warning(f"⚠️ {w}")

     st.session_state[S.DF_FILTERED] = outcome.df
     st.session_state[S.SHOW_COLS] = display_cols

 if S.DF_FILTERED in st.session_state:
     df_filtered: pd.DataFrame = st.session_state[S.DF_FILTERED]
     show_cols_saved = st.session_state.get(S.SHOW_COLS, display_cols)

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

         st.markdown("---")
         st.subheader("✉️ Kişiye Özel Soğuk Mail Taslağı")

         def _make_label(row: pd.Series) -> str:
             name = f"{row.get('First Name', '')} {row.get('Last Name', '')}".strip()
             company = row.get("Company Name", "")
             title = row.get("Title", "")
             parts = [p for p in [name, title, company] if p]
             return " · ".join(parts) if parts else f"Satır {row.name}"

         labels = [_make_label(df_filtered.iloc[i]) for i in range(len(df_filtered))]
         selected_label = st.selectbox(
             "Kişi seçin",
             options=labels,
             help="Mail taslağı oluşturulacak kişiyi seçin.",
         )
         selected_idx = labels.index(selected_label)
         selected_person = df_filtered.iloc[selected_idx].to_dict()

         company_name = (selected_person.get("Company Name") or "").strip()
         cached_profile = _get_cached_intent(company_name) if company_name else None

         intent_col1, intent_col2 = st.columns([1, 1])
         with intent_col1:
             intent_clicked = st.button(
                 "🔍 Niyet Analizi Yap",
                 disabled=not company_name,
                 help=(
                     "Şirket için Google Search Grounding ile gerçek niyet sinyallerini topla. "
                     "24 saat içinde aynı şirket için tekrar çağrılmaz (free-tier koruması)."
                 ),
             )
         with intent_col2:
             if cached_profile:
                 st.markdown(
                     _level_badge(cached_profile.intent_level, cached_profile.intent_score),
                     unsafe_allow_html=True,
                 )
                 st.caption(
                     f"Önbellekten · {cached_profile.last_intent_update.strftime('%Y-%m-%d %H:%M')} UTC"
                 )

         if intent_clicked and company_name:
             if cached_profile:
                 st.info("ℹ️ Bu şirket için 24 saat içinde niyet analizi yapıldı, önbellek kullanıldı.")
                 profile = cached_profile
             else:
                 with st.spinner(f"{company_name} için Google ile niyet sinyalleri aranıyor…"):
                     try:
                         profile = enrich_intent(
                             gemini_client,
                             unique_id=company_name.lower(),
                             company_name=company_name,
                             website=str(selected_person.get("Website", "") or ""),
                             country=str(selected_person.get("Country", "") or ""),
                         )
                         _set_cached_intent(profile)
                     except Exception as e:
                         st.error(f"Niyet analizi başarısız: {e}")
                         profile = None

             if profile:
                 st.markdown(_level_badge(profile.intent_level, profile.intent_score), unsafe_allow_html=True)
                 if profile.intent_signals:
                     st.markdown("**Tespit edilen sinyaller:**")
                     for s in profile.intent_signals:
                         st.markdown(f"- {s}")
                 else:
                     st.caption("Belirgin bir niyet sinyali bulunamadı.")
                 if profile.grounding_urls:
                     with st.expander(f"🔗 Kaynaklar ({len(profile.grounding_urls)})"):
                         for url in profile.grounding_urls:
                             st.markdown(f"- {url}")

         if st.button("🪄 Intent + Mail Taslağı Oluştur", type="primary"):
             profile_for_email = _get_cached_intent(company_name) if company_name else None
             with st.spinner(f"Gemini, {selected_label} için içerik oluşturuyor…"):
                 try:
                     result = generate_outreach(gemini_client, selected_person, profile_for_email)
                     st.session_state[S.OUTREACH_RESULT] = result
                     st.session_state[S.OUTREACH_PERSON] = selected_label
                 except Exception as e:
                     st.error(f"Mail taslağı oluşturulamadı: {e}")

         if S.OUTREACH_RESULT in st.session_state:
             result = st.session_state[S.OUTREACH_RESULT]
             person_label = st.session_state.get(S.OUTREACH_PERSON, "")

             with st.expander(f"📬 {person_label} için Üretilen İçerik", expanded=True):
                 st.markdown("#### 🎯 Sentetik Satın Alma Niyeti")
                 st.info(result.intent)

                 st.markdown("#### 📧 Soğuk Satış Maili Taslağı")
                 email_text = result.email_draft
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
                     data=result.email_draft.encode("utf-8"),
                     file_name=f"outreach_{selected_idx}.txt",
                     mime="text/plain",
                 )

 with st.expander("📂 Ham Veri Önizlemesi (ilk 5 satır)", expanded=False):
     st.dataframe(df_full.head(), use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════
# TAB 2 — Multi-step Agent (Chat Interface)
# ═══════════════════════════════════════════════════════════════════════════
with tab_agent:
 st.markdown(
     "**Sohbetçi AI Asistan.** "
     "Karmaşık görevleri tek sorguda çalıştır. Agent, ihtiyacına göre filtreleme · niyet analizi · mail taslağı araçlarını çağırır."
 )

 # ── Initialize chat history and intent cache ────────────────────────────
 if "agent_chat_history" not in st.session_state:
     st.session_state["agent_chat_history"] = []
 if "agent_intent_cache" not in st.session_state:
     st.session_state["agent_intent_cache"] = {}

 # ── Display chat history ────────────────────────────────────────────────
 for msg in st.session_state["agent_chat_history"]:
     with st.chat_message(msg["role"], avatar="🧠" if msg["role"] == "assistant" else "👤"):
         st.markdown(msg["content"])

         # Show tool calls if available (assistant messages)
         if msg.get("tool_calls"):
             with st.expander(f"🔧 Araç Çağrıları — {len(msg['tool_calls'])}"):
                 for i, tc in enumerate(msg["tool_calls"], 1):
                     st.markdown(f"**{i}. `{tc.name}`** _{tc.duration_ms} ms_")
                     st.code(json.dumps(tc.args, ensure_ascii=False, indent=2), language="json")
                     st.caption(f"Sonuç: {tc.result_summary}")

         # Show outreach drafts if available
         if msg.get("outreach_drafts"):
             st.markdown(f"#### ✉️ Taslaklar ({len(msg['outreach_drafts'])})")
             for i, draft in enumerate(msg["outreach_drafts"], 1):
                 with st.expander(f"Taslak {i}", expanded=(i == 1)):
                     st.markdown("**🎯 Niyet:**")
                     st.info(draft.intent)
                     st.markdown("**📧 Mail:**")
                     email_text = draft.email_draft
                     if email_text.startswith("Subject:"):
                         lines = email_text.split("\n", 1)
                         st.markdown(f"**{lines[0]}**")
                         st.markdown("---")
                         st.markdown(lines[1].strip() if len(lines) > 1 else "")
                     else:
                         st.markdown(email_text)
                     st.download_button(
                         label="⬇️ İndir",
                         data=draft.email_draft.encode("utf-8"),
                         file_name=f"agent_outreach_{i}.txt",
                         mime="text/plain",
                         key=f"dl_agent_{i}_{msg.get('timestamp', '')}",
                     )

 # ── Chat input at bottom ────────────────────────────────────────────────
 user_input = st.chat_input(
     "Görevinizi yazın (Örn: İstanbul'daki 3 fintech şirketini bul, niyet analizi yap ve CEO'larına mail taslağı oluştur)",
     key="agent_chat_input",
 )

 if user_input:
     # ── Injection guard ────────────────────────────────────────────────
     guard = check_prompt_injection(user_input)
     if not guard.safe:
         st.error(f"⛔ Güvenlik kontrolü başarısız: {guard.reason}")
     else:
         # Add user message to history
         st.session_state["agent_chat_history"].append({
             "role": "user",
             "content": user_input,
             "timestamp": datetime.utcnow().isoformat(),
         })

         # Show user message
         with st.chat_message("user", avatar="👤"):
             st.markdown(user_input)

         # Run agent
         with st.spinner("🧠 AI asistan çalışıyor… (çok adımlı Gemini çağrıları yapılabilir)"):
             agent_result = run_agent(
                 client=gemini_client,
                 query=user_input,
                 df=df_full,
                 intent_cache=st.session_state["agent_intent_cache"],
                 confirmed_batch=False,
             )

         # Build assistant response
         response_content = ""
         if agent_result.injection_flagged:
             response_content = "⛔ Prompt injection tespit edildi — sorgu engellendi."
         elif agent_result.error:
             response_content = f"❌ Hata: {agent_result.error}"
         else:
             response_content = agent_result.answer

         # Add assistant message to history
         st.session_state["agent_chat_history"].append({
             "role": "assistant",
             "content": response_content,
             "tool_calls": agent_result.tool_calls,
             "outreach_drafts": agent_result.outreach_drafts,
             "pii_warnings": agent_result.pii_warnings,
             "timestamp": datetime.utcnow().isoformat(),
         })

         st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# TAB 3 — Campaign Manager (Phase 1: Autonomous Campaign Automation)
# ═══════════════════════════════════════════════════════════════════════════
with tab_campaign:
 if not db_available():
     st.error("❌ Supabase bağlantısı yok. Kampanya yöneticisi kullanabilmek için Supabase ayarlanmalıdır.")
     st.stop()

 st.markdown(
     "**24/7 Otonom Kampanya Yönetimi.** "
     "Doğal dilde filtre yapın, otomatik niyet analizi ve mail taslağı oluşturun, "
     "zamanlanmış çalıştırma ile ilgili kişileri keşfedin."
 )

 # ── Campaign creation form ──────────────────────────────────────────────
 st.subheader("📝 Yeni Kampanya Oluştur")

 campaign_cols = st.columns([2, 1])
 with campaign_cols[0]:
     campaign_name = st.text_input(
         "Kampanya Adı",
         placeholder="Örn: Eylül Fintech Kampanyası",
         help="Bu kampanyanın adı (raporlamada görüntülenecek)."
     )

 with campaign_cols[1]:
     min_score = st.number_input(
         "Min. Niyet Skoru",
         min_value=1,
         max_value=10,
         value=5,
         help="Bu skor altındaki şirketler taslak oluşturulmayacak."
     )

 campaign_query = st.text_area(
     "Filtre Sorgusu (Doğal Dil)",
     placeholder="Örn: İstanbul'da fintech sektöründe 100-1000 çalışan VP'ler",
     height=60,
     help="Doğal dilde yazın; Gemini Function Calling otomatik filtre oluşturacak."
 )

 schedule_options = {
     "Manuel": "manual",
     "Her Gün 09:00": "daily 09:00",
     "Her Pazartesi 09:00": "weekly Monday",
     "Her Çarşamba 09:00": "weekly Wednesday",
     "Her Cuma 09:00": "weekly Friday",
 }
 schedule_display = st.selectbox(
     "Çalıştırma Zamanı",
     options=list(schedule_options.keys()),
     help="Manuel: Anında; Diğerleri: Belirtilen saatte otomatik çalışacak (APScheduler)."
 )
 schedule_cron = schedule_options[schedule_display]

 # ── Create campaign button ──────────────────────────────────────────────
 if st.button("🚀 Kampanya Oluştur & Zamanla", type="primary", disabled=not campaign_name or not campaign_query):
     with st.spinner("Kampanya oluşturuluyor…"):
         campaign = Campaign(
             name=campaign_name,
             query=campaign_query,
             min_intent_score=min_score,
             scheduled_at=schedule_cron if schedule_cron != "manual" else None,
             status="draft"
         )
         campaign_dict = campaign.to_dict()
         created = create_campaign(campaign_dict)

         if created:
             campaign_id = created["id"]
             scheduler = get_scheduler()

             # Schedule the campaign if not manual
             if schedule_cron != "manual":
                 schedule_campaign(scheduler, campaign_id, schedule_cron)
                 st.success(f"✅ Kampanya oluşturuldu ve **{schedule_display}** için zamanlandı.")
             else:
                 st.success(f"✅ Kampanya oluşturuldu (manuel mod).")

             # Save campaign ID for quick access
             st.session_state["last_campaign_id"] = campaign_id
         else:
             st.error("❌ Kampanya oluşturulamadı. Lütfen daha sonra tekrar deneyin.")

 st.markdown("---")

 # ── Active campaigns list ───────────────────────────────────────────────
 st.subheader("📊 Aktif Kampanyalar")

 campaigns = list_campaigns(limit=20)
 if not campaigns:
     st.info("Henüz kampanya oluşturulmadı.")
 else:
     for camp in campaigns:
         camp_id = camp.get("id", "")
         camp_name = camp.get("name", "—")
         camp_status = camp.get("status", "draft")
         camp_draft_count = camp.get("draft_count", 0)
         camp_scheduled = camp.get("scheduled_at", "—")
         camp_created = camp.get("created_at", "—")

         col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

         with col1:
             # Status badge
             status_color = {"draft": "🔵", "ready": "🟢", "executing": "🟡", "completed": "✅"}
             status_badge = status_color.get(camp_status, "⚪")
             st.markdown(f"**{status_badge} {camp_name}**")
             st.caption(f"ID: {camp_id[:8]}...")

         with col2:
             st.metric("Taslaklar", camp_draft_count)

         with col3:
             st.metric("Durum", camp_status)

         with col4:
             st.metric("Zamanla", camp_scheduled if camp_scheduled else "Manuel")

         # Action buttons
         action_col1, action_col2, action_col3 = st.columns(3)

         with action_col1:
             if st.button("▶️ Test Çalıştır", key=f"test_run_{camp_id}", help="Kampanyayı hemen çalıştır"):
                 with st.spinner(f"'{camp_name}' çalıştırılıyor…"):
                     try:
                         execute_campaign(camp_id, gemini_client, df_full)
                         st.rerun()
                     except Exception as e:
                         st.error(f"Kampanya çalıştırma hatası: {e}")

         with action_col2:
             if camp_status == "ready" and camp_draft_count > 0:
                 # Generate CSV download
                 db_client = get_supabase_client()
                 result = db_client.table("campaigns").select("results_json").eq("id", camp_id).execute()
                 if result.data and result.data[0].get("results_json"):
                     drafts_data = result.data[0]["results_json"].get("drafts", [])
                     if drafts_data:
                         import io
                         import csv

                         output = io.StringIO()
                         fieldnames = ["first_name", "last_name", "email", "company_name", "subject", "body", "intent_score", "industry"]
                         writer = csv.DictWriter(output, fieldnames=fieldnames)
                         writer.writeheader()

                         for draft in drafts_data:
                             writer.writerow({k: draft.get(k, "") for k in fieldnames})

                         csv_bytes = output.getvalue().encode("utf-8-sig")
                         st.download_button(
                             label="⬇️ CSV İndir",
                             data=csv_bytes,
                             file_name=f"{camp_name.replace(' ', '_')}_drafts.csv",
                             mime="text/csv",
                             key=f"csv_{camp_id}"
                         )

         with action_col3:
             if st.button("❌ Sil", key=f"delete_{camp_id}", help="Kampanyayı ve taslakları sil"):
                 try:
                     get_supabase_client().table("campaigns").delete().eq("id", camp_id).execute()
                     st.success(f"✅ Kampanya silindi.")
                     st.rerun()
                 except Exception as e:
                     st.error(f"Silme hatası: {e}")

         st.divider()

 st.markdown("---")

 # ── APScheduler info ───────────────────────────────────────────────────
 with st.expander("ℹ️ APScheduler Durumu", expanded=False):
     try:
         scheduler = get_scheduler()
         st.markdown(f"**Scheduler çalışıyor:** {scheduler.running}")
         jobs = scheduler.get_jobs()
         st.markdown(f"**Zamanlanmış İşler:** {len(jobs)}")
         if jobs:
             for job in jobs:
                 st.markdown(f"- `{job.id}` → Sonraki çalışma: {job.next_run_time}")
     except Exception as e:
         st.warning(f"⚠️ Scheduler bilgisi alınamadı: {e}")
