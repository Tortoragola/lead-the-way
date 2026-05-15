"""Gemini function-calling tool declarations."""
from __future__ import annotations

from google.genai import types


FILTER_DATAFRAME_TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="filter_dataframe",
            description=(
                "B2B iletişim veritabanını verilen kriterlere göre filtreler. "
                "Kullanıcının doğal dildeki isteğini sütun bazlı filtre kurallarına dönüştür."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "filters": types.Schema(
                        type=types.Type.ARRAY,
                        description="Uygulanacak filtre kuralları listesi",
                        items=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "column": types.Schema(
                                    type=types.Type.STRING,
                                    description=(
                                        "Filtrelenecek sütun adı. Geçerli değerler: "
                                        "First Name, Last Name, Title, Company Name, Email, "
                                        "Seniority, Departments, Sub Departments, Industry, "
                                        "City, State, Country, Company City, Company Country, "
                                        "# Employees, Annual Revenue, Technologies, Keywords"
                                    ),
                                ),
                                "operator": types.Schema(
                                    type=types.Type.STRING,
                                    description=(
                                        "Filtre operatörü. "
                                        "KURAL: Title, Departments, Industry, Technologies, Keywords için "
                                        "DAIMA `contains` kullan — asla `equals` değil (değerler birleşik olabilir). "
                                        "Country, Seniority için `equals` veya `in_list` kullanabilirsin. "
                                        "Sayısal karşılaştırmalar için `greater_than` / `less_than`."
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
                                        "Filtre değeri. in_list için virgülle ayrılmış değerler. "
                                        "Türkçe terimler İngilizce karşılıklarıyla eşleştirilir "
                                        "(örn. 'pazarlama' → 'marketing', 'müdür' → 'manager'). "
                                        "Unvan+departman kombinasyonunda tam ifade kullan: "
                                        "örn. 'Marketing Manager' ('Manager' + ayrı 'Marketing' değil)."
                                    ),
                                ),
                            },
                            required=["column", "operator", "value"],
                        ),
                    ),
                    "logic": types.Schema(
                        type=types.Type.STRING,
                        description=(
                            "Filtreler arası mantık operatörü. "
                            "Hem Title hem Departments filtreliyorsan OR kullan; "
                            "bağımsız kriterler için (Country + Seniority gibi) AND kullan."
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
                "Bir şirket için Google Search Grounding ile gerçek satın alma niyeti "
                "sinyallerini topla ve 1-10 arası skor üret. Aynı şirket için 24 saat "
                "içinde tekrar çağrılmamalıdır."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "unique_id": types.Schema(
                        type=types.Type.STRING,
                        description="Şirketin benzersiz kimliği (veya normalize edilmiş adı).",
                    ),
                    "company_name": types.Schema(
                        type=types.Type.STRING,
                        description="Şirketin tam adı.",
                    ),
                    "website": types.Schema(
                        type=types.Type.STRING,
                        description="Şirketin web sitesi veya ülkesi (opsiyonel).",
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
        "Bir kişi için kişiselleştirilmiş soğuk satış maili taslağı oluştur. "
        "Aynı şirket için daha önce enrich_company_intent çağrıldıysa, "
        "niyet sinyalleri otomatik olarak maile eklenir."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "first_name":   types.Schema(type=types.Type.STRING, description="Kişinin adı."),
            "last_name":    types.Schema(type=types.Type.STRING, description="Kişinin soyadı."),
            "title":        types.Schema(type=types.Type.STRING, description="Unvanı."),
            "company_name": types.Schema(type=types.Type.STRING, description="Şirket adı."),
            "industry":     types.Schema(type=types.Type.STRING, description="Sektör."),
            "city":         types.Schema(type=types.Type.STRING, description="Şehir / Ülke."),
            "email":        types.Schema(type=types.Type.STRING, description="E-posta adresi."),
            "employees":    types.Schema(type=types.Type.STRING, description="Çalışan sayısı (metin)."),
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
                    enum=["DÜŞÜK", "ORTA", "YÜKSEK"],
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


def get_agent_tools(db_mode: bool) -> list[types.Tool]:
    """Return the tool set for the multi-step agent loop.

    DB mode:  semantic layer tools + common tools (no filter_dataframe).
    CSV mode: filter_dataframe + common tools (legacy path).
    """
    common = [
        ENRICH_COMPANY_INTENT_TOOL.function_declarations[0],
        _GENERATE_OUTREACH_DRAFT_DECL,
    ]
    mode_decls = _SEMANTIC_DECLS if db_mode else [FILTER_DATAFRAME_TOOL.function_declarations[0]]
    return [types.Tool(function_declarations=common + mode_decls)]
