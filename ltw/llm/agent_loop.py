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

MAX_TURNS = 12
BATCH_CONFIRM_THRESHOLD = 5

# Tools whose results are pure data fetches — agent should use Lite model on the
# NEXT turn to fill args / summarize before deciding the next reasoning step.
# suggest_actions is intentionally excluded: it is a terminal call handled before dispatch.
_DATA_FETCH_TOOLS: frozenset[str] = frozenset({
    "filter_dataframe",
    "search_people",
    "get_companies_by_sector",
    "get_high_intent_leads",
    "get_contacts_for_company",
    "search_companies",
    "count_leads",
    "get_distinct_values",
    "get_company_details",
})


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
    # Populated when the agent calls suggest_actions instead of plain-text questions
    suggested_actions: list[dict] = field(default_factory=list)  # list of action dicts
    actions_context: str = ""  # sentence shown above the action checkboxes


# ── Internal context ─────────────────────────────────────────────────────────

@dataclass
class _AgentContext:
    client: genai.Client
    df: pd.DataFrame | None
    intent_cache: dict  # company_name.lower() → CompanyIntentProfile
    outreach_drafts: list[OutreachResult] = field(default_factory=list)


# ── System prompt ─────────────────────────────────────────────────────────────

def _build_system_prompt(db_mode: bool) -> str:  # noqa: C901
    if db_mode:
        data_section = """## AVAILABLE DATA TOOLS (DB mode)
- search_people: Search contacts by title, seniority, department, country, industry.
  USE THIS FIRST for people searches. Filterable columns:
    title (ILIKE), seniority (exact: C-Level/VP/Director/Manager/Senior/Entry),
    department (ILIKE), country (exact), industry (ILIKE).
- count_leads: Count matching contacts without fetching. Use before a broad search.
- get_distinct_values: Discover valid values in a column (country/industry/seniority/department/city).
- get_companies_by_sector: Filter companies by sector keyword + optional country + intent level.
- get_high_intent_leads: Companies with intent_score >= min_score.
- get_contacts_for_company: People at a company (requires unique_id from a prior company search).
- search_companies: ILIKE search on company name.
- get_company_details: Full profile of one company by unique_id."""
    else:
        data_section = """## AVAILABLE DATA TOOLS (CSV mode)
- filter_dataframe: Filter the B2B contact CSV by natural-language criteria."""

    return f"""You are Lead The Way, an AI B2B Sales Development Representative assistant.
Your job: find relevant contacts in the database and generate personalized cold outreach emails.

{data_section}

## ENRICHMENT & OUTREACH TOOLS
- enrich_company_intent: Fetch real purchase-intent signals via Google Search (24-hour cache).
- generate_outreach_draft: Generate a personalized cold email for one contact.

## SEARCH STRATEGY — MANDATORY BEFORE EVERY PEOPLE SEARCH
Step 1 EXPAND: Before searching, reason about ALL synonyms for the user's request:
  - Titles: "sales manager" → head of sales, VP sales, sales director, commercial manager
  - Departments: "marketing" → growth, demand generation, brand
  - Seniority: map user terms → C-Level, VP, Director, Manager, Senior, Entry
  - Industries: "fintech" → financial technology, financial services, banking technology
Step 2 COVER: Call search_people multiple times (one per major synonym variant). Be broad.
Step 3 DEDUPLICATE: Remove contacts with the same email before presenting results.

## STANDARD WORKFLOW
1. Use count_leads first if unsure how many results to expect.
2. Search for contacts (with synonym expansion). If zero results, widen the search and retry.
3. Present a clear summary: name, title, company, country, email.
4. If user wants intent analysis: call enrich_company_intent — MAX 4 parallel calls (rate limit).
5. If user wants emails: call generate_outreach_draft — MAX 4 parallel calls (rate limit).
6. If ≥5 outreach drafts needed, ask the user for confirmation first.
7. On follow-up questions, use conversation context — do not re-search from scratch.

## ACTION SUGGESTIONS
When you naturally want to ask the user "would you like intent analysis or email drafts?" or
similar follow-up questions, call suggest_actions instead of asking in plain text.
Rules for suggest_actions:
- It is a TERMINAL call: do NOT combine it with any other tool in the same response turn.
- Provide 2-4 meaningful, distinct action options with Turkish labels.
- After calling it, stop immediately. Do not produce any additional text.
- Do NOT call it if the user has already given a clear instruction.

## HARD RULES
- Never hallucinate. Only use data returned by tools. Never invent names, emails, or companies.
- Never fire more than 4 enrich_company_intent or generate_outreach_draft calls in one batch.
- unique_id for get_contacts_for_company comes from company rows — never guess it.
- Always respond to the user in Turkish."""


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

        elif name == "search_people":
            from ..llm.semantic import search_people
            res = search_people(
                title=args.get("title"),
                seniority=args.get("seniority"),
                department=args.get("department"),
                country=args.get("country"),
                industry=args.get("industry"),
                limit=int(args.get("limit", 50)),
            )
            return json.dumps({"total": res.total, "rows": [r.__dict__ for r in res.rows]},
                              ensure_ascii=False, default=str)

        elif name == "count_leads":
            from ..llm.semantic import count_leads
            res = count_leads(
                title=args.get("title"),
                seniority=args.get("seniority"),
                department=args.get("department"),
                country=args.get("country"),
                industry=args.get("industry"),
            )
            return json.dumps({"count": res.rows[0]["count"] if res.rows else 0},
                              ensure_ascii=False)

        elif name == "get_company_details":
            from ..llm.semantic import get_company_details
            res = get_company_details(unique_id=args.get("unique_id", ""))
            return json.dumps({"total": res.total, "rows": [r.__dict__ for r in res.rows]},
                              ensure_ascii=False, default=str)

        elif name == "get_distinct_values":
            from ..llm.semantic import get_distinct_values
            res = get_distinct_values(column=args.get("column", ""))
            values = res.rows[0]["values"] if res.rows else []
            return json.dumps({"column": args.get("column"), "values": values},
                              ensure_ascii=False)

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})

    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── Main loop ─────────────────────────────────────────────────────────────────

def run_agent(
    client: genai.Client,
    query: str,
    df: pd.DataFrame | None = None,
    intent_cache: dict | None = None,
    confirmed_batch: bool = False,
    conversation_history: list[dict] | None = None,
) -> AgentRunResult:
    """Run the multi-step agent loop for a single user query.

    Args:
        client:               Gemini client.
        query:                Natural-language query from the user.
        df:                   DataFrame for CSV mode; None for DB mode.
        intent_cache:         Mutable dict (company_name.lower() → CompanyIntentProfile).
                              Updated in-place so the UI can persist it in session_state.
        confirmed_batch:      If True, batch confirmation already given — proceed even if ≥5 drafts.
        conversation_history: Past messages as list of {"role": "user"|"assistant", "content": str}.
                              Injected into the contents list before the current query.
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

    # Build conversation contents: inject history then current query
    contents: list[types.Content] = []
    for msg in (conversation_history or []):
        role = "user" if msg.get("role") == "user" else "model"
        contents.append(
            types.Content(role=role, parts=[types.Part(text=msg.get("content", ""))])
        )
    contents.append(
        types.Content(role="user", parts=[types.Part(text=query)])
    )

    tool_calls: list[ToolCallRecord] = []
    # Track which tools were called in the previous turn to decide model for next turn.
    # Use Lite only after a pure data-fetch turn; use Flash for initial and reasoning turns.
    _last_turn_tool_names: set[str] = set()

    for _turn in range(MAX_TURNS):
        # Use Lite only if the previous turn was entirely data-fetch tools.
        use_lite = bool(_last_turn_tool_names) and _last_turn_tool_names.issubset(_DATA_FETCH_TOOLS)
        model = MODEL_EXTRACTION if use_lite else MODEL_REASONING

        # On the final allowed turn, switch to AUTO so the model can produce a text answer
        # instead of being forced into another function call with nowhere to go.
        # On all other turns, use ANY to prevent the model from dropping into chit-chat
        # mid-chain when it should still be calling tools.
        is_last_turn = (_turn == MAX_TURNS - 1)
        fc_mode = "AUTO" if is_last_turn else "ANY"

        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=tool_set,
                    tool_config=types.ToolConfig(
                        function_calling_config=types.FunctionCallingConfig(mode=fc_mode),
                    ),
                ),
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

        # suggest_actions is a terminal call — return early without sending FunctionResponse
        suggest_part = next(
            (p for p in fc_parts if p.function_call.name == "suggest_actions"), None
        )
        if suggest_part is not None:
            sa_args = dict(suggest_part.function_call.args) if suggest_part.function_call.args else {}
            # Any text parts produced alongside the call become the answer preamble
            preamble = "\n".join(p.text for p in text_parts).strip()
            return AgentRunResult(
                answer=preamble,
                tool_calls=tool_calls,
                outreach_drafts=ctx.outreach_drafts,
                suggested_actions=list(sa_args.get("actions", [])),
                actions_context=str(sa_args.get("context_summary", "")),
            )

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

        # Batch confirmation check BEFORE executing outreach calls
        outreach_in_turn = sum(
            1 for p in fc_parts if p.function_call.name == "generate_outreach_draft"
        )
        if not confirmed_batch and (len(ctx.outreach_drafts) + outreach_in_turn) >= BATCH_CONFIRM_THRESHOLD:
            return AgentRunResult(
                answer="",
                tool_calls=tool_calls,
                outreach_drafts=ctx.outreach_drafts,
                needs_batch_confirm=True,
                pending_outreach_count=len(ctx.outreach_drafts) + outreach_in_turn,
            )

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
        _last_turn_tool_names = {p.function_call.name for p in fc_parts}

    return AgentRunResult(
        answer=(
            f"Maksimum tur sayısına ({MAX_TURNS}) ulaşıldı. "
            "Lütfen görevinizi daha küçük adımlara bölün."
        ),
        tool_calls=tool_calls,
        outreach_drafts=ctx.outreach_drafts,
    )
