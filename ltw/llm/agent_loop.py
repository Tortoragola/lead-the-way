"""Multi-step agent loop with sequential/parallel function calling.

Model routing (free-tier):
  - Fresh query / reasoning turns  → MODEL_REASONING  (gemini-3-flash)
  - Pure arg-fill turns (after FunctionResponse) → MODEL_EXTRACTION (gemini-3.1-flash-lite)

Batch confirmation: if the agent wants to draft ≥BATCH_CONFIRM_THRESHOLD outreach
emails, it stops early and signals for user confirmation before executing.

Thought-signature preservation: when Gemini returns a thought_signature on a
function_call Part, we echo it back in the FunctionResponse so multi-step
reasoning chains are not broken.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import pandas as pd
from google import genai
from google.genai import types

from ..db import db_available, write_audit_log
from ..filters import filter_dataframe, normalize_filters
from ..models import CompanyIntentProfile, OutreachResult
from ..security import check_prompt_injection
from .client import MODEL_EXTRACTION, MODEL_REASONING
from .intent import enrich_intent
from .outreach import generate_outreach
from .tools import get_agent_tools

MAX_TURNS = 6
BATCH_CONFIRM_THRESHOLD = 5


# ── Result types ─────────────────────────────────────────────────────────────

@dataclass
class ToolCallRecord:
    name: str
    args: dict
    result_summary: str
    duration_ms: int


@dataclass
class AgentRunResult:
    answer: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    outreach_drafts: list[OutreachResult] = field(default_factory=list)
    needs_batch_confirm: bool = False
    pending_outreach_count: int = 0
    error: str | None = None
    injection_flagged: bool = False
    pii_warnings: list[str] = field(default_factory=list)


# ── Internal context ─────────────────────────────────────────────────────────

@dataclass
class _AgentContext:
    client: genai.Client
    df: pd.DataFrame | None
    intent_cache: dict  # company_name.lower() → CompanyIntentProfile
    outreach_drafts: list[OutreachResult] = field(default_factory=list)


# ── System prompt ─────────────────────────────────────────────────────────────

def _build_system_prompt(db_mode: bool) -> str:
    if db_mode:
        data_tools = (
            "- get_companies_by_sector: Sektör + ülke + niyet seviyesine göre şirket filtrele\n"
            "- get_high_intent_leads: Yüksek niyet skorlu şirketleri getir\n"
            "- get_contacts_for_company: Bir şirketteki kişileri getir (unique_id ile)\n"
            "- search_companies: Şirket adında arama yap\n"
        )
    else:
        data_tools = (
            "- filter_dataframe: CSV veritabanını doğal dil kriterlerine göre filtrele\n"
        )

    return (
        "Sen Lead The Way AI SDR asistanısın. Kullanıcının B2B satış hedeflerini "
        "gerçekleştirmek için elindeki araçları sıralı veya paralel olarak çağırırsın.\n\n"
        "Kullanabileceğin araçlar:\n"
        + data_tools
        + "- enrich_company_intent: Şirket için Google Search ile gerçek niyet sinyali bul (24h cache uygula)\n"
        "- generate_outreach_draft: Kişiye özel soğuk satış maili taslağı oluştur\n\n"
        "Kurallar:\n"
        "- Birden fazla şirket/kişi için araçları paralel çağır (aynı anda birden fazla function_call).\n"
        "- 5 veya daha fazla outreach draft oluşturmadan önce kullanıcıdan onay bekle.\n"
        "- Yanıtlarını Türkçe ver.\n"
        "- Hallucination yapma; yalnızca araç sonuçlarındaki verileri kullan.\n"
        "- Araç sonuçlarını özetle; ham JSON döndürme."
    )


# ── Tool dispatcher ───────────────────────────────────────────────────────────

def _dispatch_tool(name: str, args: dict, ctx: _AgentContext) -> str:
    """Execute one tool call. Returns JSON string (error-safe)."""
    try:
        # ── CSV filter ────────────────────────────────────────────────────
        if name == "filter_dataframe":
            if ctx.df is None:
                return json.dumps({"error": "CSV modu aktif değil."})
            filters = [dict(f) for f in args.get("filters", [])]
            filters, norm_notes = normalize_filters(filters)
            logic = args.get("logic", "AND")
            outcome = filter_dataframe(ctx.df, filters, logic)
            outcome.warnings = norm_notes + outcome.warnings
            rows = json.loads(
                outcome.df.head(50).to_json(orient="records", force_ascii=False)
            )
            return json.dumps(
                {"total": len(outcome.df), "shown": len(rows), "rows": rows, "warnings": outcome.warnings},
                ensure_ascii=False, default=str,
            )

        # ── Intent enrichment ─────────────────────────────────────────────
        elif name == "enrich_company_intent":
            company = str(args.get("company_name", "")).strip()
            uid = str(args.get("unique_id", company.lower())).strip()
            cache_key = company.lower()
            if cache_key in ctx.intent_cache:
                profile = ctx.intent_cache[cache_key]
            else:
                profile = enrich_intent(
                    ctx.client,
                    unique_id=uid,
                    company_name=company,
                    website=str(args.get("website", "") or ""),
                    country=str(args.get("country", "") or ""),
                )
                ctx.intent_cache[cache_key] = profile
            return json.dumps({
                "intent_score":   profile.intent_score,
                "intent_level":   profile.intent_level.value,
                "intent_signals": profile.intent_signals,
                "grounding_urls": profile.grounding_urls,
            }, ensure_ascii=False)

        # ── Outreach draft ────────────────────────────────────────────────
        elif name == "generate_outreach_draft":
            person = {
                "First Name":   str(args.get("first_name", "") or ""),
                "Last Name":    str(args.get("last_name", "") or ""),
                "Title":        str(args.get("title", "") or ""),
                "Company Name": str(args.get("company_name", "") or ""),
                "Industry":     str(args.get("industry", "") or ""),
                "City":         str(args.get("city", "") or ""),
                "Country":      str(args.get("country", "") or ""),
                "Email":        str(args.get("email", "") or ""),
                "# Employees":  str(args.get("employees", "") or ""),
            }
            company_key = person["Company Name"].strip().lower()
            intent_profile = ctx.intent_cache.get(company_key)
            result = generate_outreach(ctx.client, person, intent_profile)
            ctx.outreach_drafts.append(result)
            preview = result.email_draft
            if len(preview) > 300:
                preview = preview[:300] + "…"
            return json.dumps({"intent": result.intent, "email_draft_preview": preview}, ensure_ascii=False)

        # ── Semantic layer (DB mode) ───────────────────────────────────────
        elif name == "get_companies_by_sector":
            from ..llm.semantic import get_companies_by_sector
            res = get_companies_by_sector(
                sector=args.get("sector", ""),
                country=args.get("country"),
                intent_level=args.get("intent_level"),
                limit=int(args.get("limit", 50)),
            )
            return json.dumps({"total": res.total, "rows": [r.__dict__ for r in res.rows]},
                              ensure_ascii=False, default=str)

        elif name == "get_high_intent_leads":
            from ..llm.semantic import get_high_intent_leads
            res = get_high_intent_leads(
                min_score=int(args.get("min_score", 8)),
                country=args.get("country"),
                limit=int(args.get("limit", 20)),
            )
            return json.dumps({"total": res.total, "rows": [r.__dict__ for r in res.rows]},
                              ensure_ascii=False, default=str)

        elif name == "get_contacts_for_company":
            from ..llm.semantic import get_contacts_for_company
            res = get_contacts_for_company(
                unique_id=args.get("unique_id", ""),
                seniority=args.get("seniority"),
            )
            return json.dumps({"total": res.total, "rows": [r.__dict__ for r in res.rows]},
                              ensure_ascii=False, default=str)

        elif name == "search_companies":
            from ..llm.semantic import search_companies
            res = search_companies(
                query=args.get("query", ""),
                limit=int(args.get("limit", 30)),
            )
            return json.dumps({"total": res.total, "rows": [r.__dict__ for r in res.rows]},
                              ensure_ascii=False, default=str)

        else:
            return json.dumps({"error": f"Bilinmeyen araç: {name}"})

    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── Main loop ─────────────────────────────────────────────────────────────────

def run_agent(
    client: genai.Client,
    query: str,
    df: pd.DataFrame | None = None,
    intent_cache: dict | None = None,
    confirmed_batch: bool = False,
) -> AgentRunResult:
    """Run the multi-step agent loop for a single user query.

    Args:
        client:           Gemini client.
        query:            Natural-language query from the user.
        df:               DataFrame for CSV mode; None for DB mode.
        intent_cache:     Mutable dict (company_name.lower() → CompanyIntentProfile).
                          Updated in-place so the UI can persist it in session_state.
        confirmed_batch:  If True, batch confirmation already given — proceed even if ≥5 drafts.
    """
    if intent_cache is None:
        intent_cache = {}

    # ── Prompt-injection guard (OWASP LLM01) ───────────────────────────────
    guard = check_prompt_injection(query)
    if not guard.safe:
        write_audit_log(
            event_type="filter",
            query_summary=query[:200],
            injection_flagged=True,
        )
        return AgentRunResult(
            answer=f"⛔ Güvenlik kontrolü başarısız: {guard.reason}",
            injection_flagged=True,
        )

    ctx = _AgentContext(client=client, df=df, intent_cache=intent_cache)
    db_mode = db_available() and df is None
    tool_set = get_agent_tools(db_mode)
    system_prompt = _build_system_prompt(db_mode)

    contents: list[types.Content] = [
        types.Content(
            role="user",
            parts=[types.Part(text=f"{system_prompt}\n\nKullanıcı: {query}")],
        )
    ]

    tool_calls: list[ToolCallRecord] = []
    last_was_function_response = False

    for _turn in range(MAX_TURNS):
        model = MODEL_EXTRACTION if last_was_function_response else MODEL_REASONING

        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(tools=tool_set),
            )
        except Exception as exc:
            return AgentRunResult(
                answer="",
                tool_calls=tool_calls,
                outreach_drafts=ctx.outreach_drafts,
                error=f"Gemini API hatası ({model}): {exc}",
            )

        parts = response.candidates[0].content.parts
        fc_parts = [p for p in parts if getattr(p, "function_call", None) is not None]
        text_parts = [p for p in parts if getattr(p, "text", None) and p.text.strip()]

        # No function calls → model returned final text
        if not fc_parts:
            raw_answer = "\n".join(p.text for p in text_parts)
            write_audit_log(
                event_type="filter",
                query_summary=query[:200],
                model_used=MODEL_REASONING,
            )
            return AgentRunResult(
                answer=raw_answer,
                tool_calls=tool_calls,
                outreach_drafts=ctx.outreach_drafts,
                pii_warnings=[],
            )

        # NOTE: Batch confirmation gate removed — campaigns auto-generate all drafts
        # without human intervention (Phase 1: Campaign Automation)

        # Append model's response to conversation history
        contents.append(types.Content(role="model", parts=parts))

        # Execute all function calls (parallel dispatch in Python)
        function_response_parts: list[types.Part] = []
        for fc_part in fc_parts:
            fc = fc_part.function_call
            name = fc.name
            args = dict(fc.args) if fc.args else {}

            t0 = time.perf_counter()
            result_json = _dispatch_tool(name, args, ctx)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)

            # Audit outreach drafts
            if name == "generate_outreach_draft":
                write_audit_log(
                    event_type="outreach_draft",
                    company_name=str(args.get("company_name", ""))[:255] or None,
                    person_email=str(args.get("email", "")) or None,
                    query_summary=query[:200],
                    model_used=MODEL_REASONING,
                )

            summary = result_json[:200] + ("…" if len(result_json) > 200 else "")
            tool_calls.append(ToolCallRecord(name=name, args=args, result_summary=summary, duration_ms=elapsed_ms))

            fr = types.FunctionResponse(
                name=name,
                response={"result": json.loads(result_json)},
            )

            # Preserve thought_signature (for thinking-capable models)
            thought_sig = getattr(fc_part, "thought_signature", None)
            if thought_sig:
                try:
                    function_response_parts.append(
                        types.Part(function_response=fr, thought_signature=thought_sig)
                    )
                except TypeError:
                    function_response_parts.append(types.Part(function_response=fr))
            else:
                function_response_parts.append(types.Part(function_response=fr))

        # Send all FunctionResponses back in one turn
        contents.append(types.Content(role="user", parts=function_response_parts))
        last_was_function_response = True

    return AgentRunResult(
        answer="Maksimum tur sayısına (6) ulaşıldı. Sorgunuzu daha spesifik hale getirin.",
        tool_calls=tool_calls,
        outreach_drafts=ctx.outreach_drafts,
    )
