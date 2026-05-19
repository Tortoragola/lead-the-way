"""Gemini function-calling tool declarations."""
from __future__ import annotations

from google.genai import types


FILTER_DATAFRAME_TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="filter_dataframe",
            description=(
                "Filter the B2B contact database by the given criteria. "
                "Convert the user's natural-language request into column-based filter rules."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "filters": types.Schema(
                        type=types.Type.ARRAY,
                        description="List of filter rules to apply.",
                        items=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "column": types.Schema(
                                    type=types.Type.STRING,
                                    description=(
                                        "Column name to filter on. Valid values: "
                                        "First Name, Last Name, Title, Company Name, Email, "
                                        "Seniority, Departments, Sub Departments, Industry, "
                                        "City, State, Country, Company City, Company Country, "
                                        "# Employees, Annual Revenue, Technologies, Keywords"
                                    ),
                                ),
                                "operator": types.Schema(
                                    type=types.Type.STRING,
                                    description=(
                                        "Filter operator. "
                                        "RULE: For Title, Departments, Industry, Technologies, Keywords "
                                        "ALWAYS use `contains` — never `equals` (values may be combined). "
                                        "For Country and Seniority use `equals` or `in_list`. "
                                        "For numeric comparisons use `greater_than` / `less_than`."
                                    ),
                                    enum=[
                                        "contains", "not_contains", "equals", "not_equals",
                                        "starts_with", "ends_with", "greater_than", "less_than",
                                        "in_list",
                                    ],
                                ),
                                "value": types.Schema(
                                    type=types.Type.STRING,
                                    description=(
                                        "Filter value. For in_list use comma-separated values. "
                                        "Always use English terms "
                                        "(e.g. 'pazarlama' → 'marketing', 'müdür' → 'manager'). "
                                        "For title+department combos use the full expression: "
                                        "e.g. 'Marketing Manager' (not 'Manager' + separate 'Marketing')."
                                    ),
                                ),
                            },
                            required=["column", "operator", "value"],
                        ),
                    ),
                    "logic": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "Logical operator between filters. "
                            "Use OR when filtering both Title and Departments; "
                            "use AND for independent criteria (e.g. Country + Seniority)."
                        ),
                        enum=["AND", "OR"],
                    ),
                },
                required=["filters"],
            ),
        )
    ]
)


ENRICH_COMPANY_INTENT_TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="enrich_company_intent",
            description=(
                "Collect real purchase-intent signals for a company via Google Search Grounding "
                "and produce a score from 1 to 10. Should not be called again for the same company "
                "within 24 hours."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "unique_id": types.Schema(
                        type=types.Type.STRING,
                        description="Unique company identifier (or normalized name).",
                    ),
                    "company_name": types.Schema(
                        type=types.Type.STRING,
                        description="Full company name.",
                    ),
                    "website": types.Schema(
                        type=types.Type.STRING,
                        description="Company website or country (optional).",
                    ),
                },
                required=["unique_id", "company_name"],
            ),
        )
    ]
)


# ── Agent tool declarations ──────────────────────────────────────────────────

_GENERATE_OUTREACH_DRAFT_DECL = types.FunctionDeclaration(
    name="generate_outreach_draft",
    description=(
        "Generate a personalized cold sales email draft for a contact. "
        "If enrich_company_intent was previously called for the same company, "
        "intent signals are automatically included in the email."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "first_name":   types.Schema(type=types.Type.STRING, description="Contact's first name."),
            "last_name":    types.Schema(type=types.Type.STRING, description="Contact's last name."),
            "title":        types.Schema(type=types.Type.STRING, description="Job title."),
            "company_name": types.Schema(type=types.Type.STRING, description="Company name."),
            "industry":     types.Schema(type=types.Type.STRING, description="Industry sector."),
            "city":         types.Schema(type=types.Type.STRING, description="City / Country."),
            "email":        types.Schema(type=types.Type.STRING, description="Email address."),
            "employees":    types.Schema(type=types.Type.STRING, description="Employee count (text)."),
        },
        required=["company_name"],
    ),
)

_SEMANTIC_DECLS = [
    types.FunctionDeclaration(
        name="search_people",
        description=(
            "Search contacts by title, seniority, department, country, and/or industry. "
            "All filters are optional and combined with AND. Title, department, and industry "
            "use partial (ILIKE) matching; seniority and country use exact (case-insensitive) matching. "
            "Call multiple times with different synonym terms to cover all variants, "
            "then deduplicate by email. "
            "Filterable columns: title, seniority (C-Level/VP/Director/Manager/Senior/Entry), "
            "department, country, industry."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "title":      types.Schema(type=types.Type.STRING, description="Title keyword (ILIKE, e.g. 'Sales Manager')."),
                "seniority":  types.Schema(type=types.Type.STRING, description="Seniority level (exact): C-Level, VP, Director, Manager, Senior, Entry."),
                "department": types.Schema(type=types.Type.STRING, description="Department keyword (ILIKE, e.g. 'Marketing')."),
                "country":    types.Schema(type=types.Type.STRING, description="Country name (exact, e.g. 'Turkey')."),
                "industry":   types.Schema(type=types.Type.STRING, description="Industry keyword (ILIKE, e.g. 'Financial')."),
                "limit":      types.Schema(type=types.Type.INTEGER, description="Max results (default: 50, max: 200)."),
            },
            required=[],
        ),
    ),
    types.FunctionDeclaration(
        name="count_leads",
        description=(
            "Count matching contacts without fetching rows. Use this before a broad search "
            "to gauge result volume. Same filter parameters as search_people."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "title":      types.Schema(type=types.Type.STRING, description="Title keyword (ILIKE)."),
                "seniority":  types.Schema(type=types.Type.STRING, description="Seniority level (exact)."),
                "department": types.Schema(type=types.Type.STRING, description="Department keyword (ILIKE)."),
                "country":    types.Schema(type=types.Type.STRING, description="Country name (exact)."),
                "industry":   types.Schema(type=types.Type.STRING, description="Industry keyword (ILIKE)."),
            },
            required=[],
        ),
    ),
    types.FunctionDeclaration(
        name="get_distinct_values",
        description=(
            "Return distinct non-null values for a people-table column. "
            "Use this to discover valid filter values before calling search_people. "
            "Allowed columns: country, industry, seniority, department, city."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "column": types.Schema(
                    type=types.Type.STRING,
                    description="Column to inspect.",
                    enum=["country", "industry", "seniority", "department", "city"],
                ),
            },
            required=["column"],
        ),
    ),
    types.FunctionDeclaration(
        name="get_companies_by_sector",
        description="Filter companies by sector keyword + optional country and intent level (DB mode).",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "sector":       types.Schema(type=types.Type.STRING, description="Sector keyword in English."),
                "country":      types.Schema(type=types.Type.STRING, description="Country name (optional)."),
                "intent_level": types.Schema(
                    type=types.Type.STRING,
                    description="Intent level filter (optional).",
                    enum=["LOW", "MEDIUM", "HIGH"],
                ),
                "limit": types.Schema(type=types.Type.INTEGER, description="Max results (default: 50)."),
            },
            required=["sector"],
        ),
    ),
    types.FunctionDeclaration(
        name="get_high_intent_leads",
        description="Return companies with intent_score >= min_score, ordered by score (DB mode).",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "min_score": types.Schema(type=types.Type.INTEGER, description="Minimum intent score 1-10 (default: 8)."),
                "country":   types.Schema(type=types.Type.STRING, description="Country filter (optional)."),
                "limit":     types.Schema(type=types.Type.INTEGER, description="Max results (default: 20)."),
            },
            required=[],
        ),
    ),
    types.FunctionDeclaration(
        name="get_contacts_for_company",
        description="Return people linked to a company by its unique_id (DB mode). unique_id comes from company search results.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "unique_id": types.Schema(type=types.Type.STRING, description="Company unique_id from a prior search result."),
                "seniority": types.Schema(type=types.Type.STRING, description="Seniority filter (optional)."),
            },
            required=["unique_id"],
        ),
    ),
    types.FunctionDeclaration(
        name="get_company_details",
        description="Return the full profile of a single company by its unique_id.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "unique_id": types.Schema(type=types.Type.STRING, description="Company unique_id."),
            },
            required=["unique_id"],
        ),
    ),
    types.FunctionDeclaration(
        name="search_companies",
        description="ILIKE search on company_name (DB mode). Use when user provides a company name.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "query": types.Schema(type=types.Type.STRING, description="Company name keyword."),
                "limit": types.Schema(type=types.Type.INTEGER, description="Max results (default: 30)."),
            },
            required=["query"],
        ),
    ),
]


_SUGGEST_ACTIONS_DECL = types.FunctionDeclaration(
    name="suggest_actions",
    description=(
        "Present the user with a structured list of follow-up action choices. "
        "Call this INSTEAD of asking 'would you like X or Y?' in plain text. "
        "This is a TERMINAL call — do NOT combine with any other tool in the same turn. "
        "Stop after calling it and wait for the user's response."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "context_summary": types.Schema(
                type=types.Type.STRING,
                description=(
                    "One sentence shown above the action choices. "
                    "Example: 'I found 6 candidates. Here is what I can do next:'"
                ),
            ),
            "actions": types.Schema(
                type=types.Type.ARRAY,
                description="List of 2-4 distinct actions the user can choose from.",
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "id": types.Schema(
                            type=types.Type.STRING,
                            description="Short snake_case identifier, e.g. 'intent_analysis'.",
                        ),
                        "label": types.Schema(
                            type=types.Type.STRING,
                            description="Short action label shown on the button, e.g. 'Run Intent Analysis'.",
                        ),
                        "description": types.Schema(
                            type=types.Type.STRING,
                            description="One-line description shown under the label.",
                        ),
                        "detail_placeholder": types.Schema(
                            type=types.Type.STRING,
                            description=(
                                "Placeholder text for the optional detail text box, "
                                "e.g. 'Which companies? (leave blank for all).'."
                            ),
                        ),
                    },
                    required=["id", "label", "description", "detail_placeholder"],
                ),
            ),
        },
        required=["context_summary", "actions"],
    ),
)


def get_agent_tools(db_mode: bool) -> list[types.Tool]:
    """Return the tool set for the multi-step agent loop.

    DB mode:  semantic layer tools + common tools (no filter_dataframe).
    CSV mode: filter_dataframe + common tools (legacy path).
    suggest_actions is always included — it is mode-agnostic.
    """
    common = [
        ENRICH_COMPANY_INTENT_TOOL.function_declarations[0],
        _GENERATE_OUTREACH_DRAFT_DECL,
        _SUGGEST_ACTIONS_DECL,
    ]
    mode_decls = _SEMANTIC_DECLS if db_mode else [FILTER_DATAFRAME_TOOL.function_declarations[0]]
    return [types.Tool(function_declarations=common + mode_decls)]
