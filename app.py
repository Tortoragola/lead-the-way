"""Lead The Way — Streamlit UI shell (chat-first).

All domain logic lives in the ``ltw`` package; this file only handles
rendering and routing user input to the package functions.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import streamlit as st

from ltw.config import get_settings
from ltw.db import db_available
from ltw.llm.agent_loop import AgentRunResult, run_agent
from ltw.llm.client import get_client
from ltw.models import CompanyIntentProfile, IntentLevel
from ltw.security import check_prompt_injection


INTENT_CACHE_TTL = timedelta(hours=24)


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

# ── Gemini client ────────────────────────────────────────────────────────────
try:
    gemini_client = get_client(get_settings().gemini_api_key)
except Exception as e:
    st.error(f"API yapılandırma hatası: {e}")
    st.stop()

# ── Session state init ───────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state["messages"] = []  # list[dict] with "role" and "content"

if "intent_cache" not in st.session_state:
    st.session_state["intent_cache"] = {}  # company_name.lower() → CompanyIntentProfile

if "pending_batch_result" not in st.session_state:
    st.session_state["pending_batch_result"] = None  # AgentRunResult awaiting confirmation

if "pending_actions" not in st.session_state:
    st.session_state["pending_actions"] = None  # list[dict] | None — action card options

if "pending_actions_context" not in st.session_state:
    st.session_state["pending_actions_context"] = ""  # sentence shown above checkboxes

if "action_card_submitted" not in st.session_state:
    st.session_state["action_card_submitted"] = False  # True after card submit, triggers agent run

if "last_query" not in st.session_state:
    st.session_state["last_query"] = ""


# ── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🎯 Lead The Way")
    st.caption("AI B2B Sales Development Representative")
    st.markdown("---")
    st.markdown(
        "**Örnek sorgular:**\n"
        "- Türkiye'deki fintech şirketlerindeki pazarlama müdürlerini bul\n"
        "- İstanbul'da SaaS sektöründeki VP ve Director seviyesindeki yöneticiler\n"
        "- En yüksek intent skorlu 5 şirketi bul, niyet analizi yap\n"
        "- Microsoft'taki kıdemli mühendislere mail taslağı oluştur\n"
        "- İngiltere'deki finans sektöründe kaç kişi var?"
    )
    st.markdown("---")
    if st.button("🗑️ Sohbeti Temizle"):
        st.session_state["messages"] = []
        st.session_state["pending_batch_result"] = None
        st.session_state["pending_actions"] = None
        st.session_state["pending_actions_context"] = ""
        st.session_state["last_query"] = ""
        st.rerun()

    st.caption(f"DB modu: {'✅ aktif' if db_available() else '❌ pasif (CSV modu)'}")


# ── Title ────────────────────────────────────────────────────────────────────
st.title("🎯 Lead The Way — AI B2B SDR")
st.caption(
    "Doğal dilde konuşun — Gemini Function Calling ile kişileri bulur, "
    "niyet analizi yapar ve kişiselleştirilmiş mail taslakları oluşturur."
)
st.divider()


# ── Render chat history ──────────────────────────────────────────────────────
def _record_result(result: AgentRunResult) -> None:
    """Append an AgentRunResult to the message history."""
    answer = result.answer or ""
    if result.error:
        answer = f"❌ Hata: {result.error}\n\n{answer}".strip()
    if result.injection_flagged:
        answer = f"⛔ Güvenlik kontrolü başarısız.\n\n{answer}".strip()

    grounding_warning = None
    for profile in st.session_state["intent_cache"].values():
        if isinstance(profile, CompanyIntentProfile) and not profile.grounding_available:
            grounding_warning = (
                "⚠️ Google Search Grounding bu API anahtarıyla kullanılamıyor. "
                "Intent skorları gerçek veriye değil, model tahminlerine dayanıyor — "
                "sonuçlar düşük güvenilirlikte. Skor 4 ile sınırlandırıldı."
            )
            break

    msg: dict = {
        "role": "assistant",
        "content": answer,
        "tool_calls": result.tool_calls or [],
        "outreach_drafts": result.outreach_drafts or [],
    }
    if grounding_warning:
        msg["grounding_warning"] = grounding_warning
    st.session_state["messages"].append(msg)

    # If the agent offered action choices, surface them as the pending card
    if result.suggested_actions:
        st.session_state["pending_actions"] = result.suggested_actions
        st.session_state["pending_actions_context"] = result.actions_context
    else:
        # A real answer clears any stale action card
        st.session_state["pending_actions"] = None
        st.session_state["pending_actions_context"] = ""


def _render_action_card() -> None:
    """Render the interactive action-choice card when the agent calls suggest_actions."""
    actions: list[dict] | None = st.session_state.get("pending_actions")
    if not actions:
        return

    context = st.session_state.get("pending_actions_context", "Şu işlemlerden birini seçin:")

    st.markdown("---")
    st.markdown(f"**{context}**")

    checked: list[tuple[dict, str]] = []  # (action, detail_text)
    for action in actions:
        aid = action.get("id", "action")
        label = action.get("label", "")
        description = action.get("description", "")
        placeholder = action.get("detail_placeholder", "Ek detay (isteğe bağlı)…")

        col_check, col_info = st.columns([1, 12])
        with col_check:
            selected = st.checkbox("", key=f"action_cb_{aid}", label_visibility="collapsed")
        with col_info:
            st.markdown(f"**{label}**  \n<small>{description}</small>", unsafe_allow_html=True)
            if selected:
                detail = st.text_input(
                    label=f"Detay — {label}",
                    placeholder=placeholder,
                    key=f"action_detail_{aid}",
                    label_visibility="collapsed",
                )
                checked.append((action, detail.strip()))

    st.markdown("")
    if st.button("▶ Seçilen İşlemleri Başlat", type="primary", key="action_card_submit"):
        if not checked:
            st.warning("En az bir işlem seçin.")
            return

        # Assemble a Turkish follow-up query from checked actions + details
        lines = ["Seçilen işlemler:"]
        for action, detail in checked:
            line = f"- {action['label']}"
            if detail:
                line += f" [Detay: {detail}]"
            lines.append(line)
        follow_up = "\n".join(lines)

        # Clear the card and submit as a new user message
        st.session_state["pending_actions"] = None
        st.session_state["pending_actions_context"] = ""
        st.session_state["messages"].append({"role": "user", "content": follow_up})
        st.session_state["last_query"] = follow_up
        st.session_state["action_card_submitted"] = True
        st.rerun()

    st.markdown("---")


def _render_outreach_drafts(drafts: list) -> None:
    if not drafts:
        return
    st.markdown(f"#### ✉️ Oluşturulan Mail Taslakları ({len(drafts)})")
    for i, draft in enumerate(drafts, 1):
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
                file_name=f"outreach_{i}.txt",
                mime="text/plain",
                key=f"dl_draft_{i}_{id(draft)}",
            )


def _render_tool_calls(tool_calls: list) -> None:
    if not tool_calls:
        return
    with st.expander(
        f"🔧 Araç Çağrı Grafiği — {len(tool_calls)} çağrı", expanded=False
    ):
        for i, tc in enumerate(tool_calls, 1):
            st.markdown(f"**{i}. `{tc.name}`** _{tc.duration_ms} ms_")
            st.code(json.dumps(tc.args, ensure_ascii=False, indent=2), language="json")
            st.caption(f"Sonuç önizleme: {tc.result_summary}")
            st.divider()


for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        # Rerender attached extras if stored
        if msg.get("tool_calls"):
            _render_tool_calls(msg["tool_calls"])
        if msg.get("outreach_drafts"):
            _render_outreach_drafts(msg["outreach_drafts"])
        if msg.get("grounding_warning"):
            st.warning(msg["grounding_warning"])

# ── Action card (suggest_actions result) ──────────────────────────────────────────
_render_action_card()
# ── Batch confirmation (if a previous result is waiting) ─────────────────────
pending: AgentRunResult | None = st.session_state.get("pending_batch_result")
if pending is not None:
    st.warning(
        f"⚠️ Agent **{pending.pending_outreach_count}** outreach taslağı oluşturmak istiyor. "
        "Devam etmek istiyor musunuz?"
    )
    bc1, bc2 = st.columns(2)
    with bc1:
        if st.button("✅ Evet, devam et", key="batch_confirm_yes"):
            with st.spinner("Onaylandı, devam ediliyor…"):
                confirmed_result = run_agent(
                    client=gemini_client,
                    query=st.session_state["last_query"],
                    intent_cache=st.session_state["intent_cache"],
                    confirmed_batch=True,
                    conversation_history=st.session_state["messages"],
                )
            st.session_state["pending_batch_result"] = None
            _record_result(confirmed_result)
            st.rerun()
    with bc2:
        if st.button("❌ İptal", key="batch_confirm_no"):
            st.session_state["pending_batch_result"] = None
            st.session_state["messages"].append({
                "role": "assistant",
                "content": "Toplu mail taslağı oluşturma iptal edildi.",
            })
            st.rerun()


# ── Chat input ───────────────────────────────────────────────────────────────
if prompt := st.chat_input("Mesajınızı yazın…"):
    # A new typed message clears any pending action card
    st.session_state["pending_actions"] = None
    st.session_state["pending_actions_context"] = ""
    st.session_state["action_card_submitted"] = False

    # Client-side injection guard
    guard = check_prompt_injection(prompt)
    if not guard.safe:
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            st.error(f"⛔ Güvenlik kontrolü başarısız: {guard.reason}")
        st.session_state["messages"].append({"role": "user", "content": prompt})
        st.session_state["messages"].append({
            "role": "assistant",
            "content": f"⛔ Güvenlik kontrolü başarısız: {guard.reason}",
        })
        st.rerun()

    # Append user message and show immediately
    st.session_state["messages"].append({"role": "user", "content": prompt})
    st.session_state["last_query"] = prompt
    active_prompt = prompt
    _from_action_card = False

elif st.session_state.get("action_card_submitted"):
    # Action card was submitted on the previous render — run agent with last_query
    st.session_state["action_card_submitted"] = False
    active_prompt = st.session_state["last_query"]
    _from_action_card = True

else:
    active_prompt = None
    _from_action_card = False

if active_prompt is not None:
    prompt = active_prompt
    # For normal chat input the message was just appended so we show it immediately.
    # For action card submissions the history loop already rendered the user bubble.
    if not _from_action_card:
        with st.chat_message("user"):
            st.markdown(prompt)

    # Run agent
    with st.chat_message("assistant"):
        with st.spinner("AI asistan düşünüyor… (birden fazla Gemini çağrısı yapılabilir)"):
            # Pass all previous messages except the one we just appended
            history = st.session_state["messages"][:-1]
            result = run_agent(
                client=gemini_client,
                query=prompt,
                intent_cache=st.session_state["intent_cache"],
                confirmed_batch=False,
                conversation_history=history,
            )

        if result.needs_batch_confirm:
            st.session_state["pending_batch_result"] = result
            st.info(
                f"⚠️ Agent **{result.pending_outreach_count}** outreach taslağı oluşturmak "
                "istiyor. Yukarıdaki onay kutusunu kullanın."
            )
            st.rerun()

        # Show answer
        answer_text = result.answer or ""
        if result.error:
            answer_text = f"❌ Hata: {result.error}\n\n{answer_text}".strip()
        st.markdown(answer_text)

        # Tool call graph
        _render_tool_calls(result.tool_calls)

        # Outreach drafts
        _render_outreach_drafts(result.outreach_drafts)

        # Grounding unavailability warning
        for profile in st.session_state["intent_cache"].values():
            if isinstance(profile, CompanyIntentProfile) and not profile.grounding_available:
                st.warning(
                    "⚠️ Google Search Grounding bu API anahtarıyla kullanılamıyor. "
                    "Intent skorları gerçek veriye değil, model tahminlerine dayanıyor. "
                    "Skor 4 ile sınırlandırıldı."
                )
                break

    _record_result(result)
    st.rerun()
