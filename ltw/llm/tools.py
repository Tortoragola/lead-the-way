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
        name="get_companies_by_sector",
        description="Sektör, ülke ve/veya niyet seviyesine göre şirketleri filtrele (DB modu).",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "sector":       types.Schema(type=types.Type.STRING, description="Sektör anahtar kelimesi (İngilizce)."),
                "country":      types.Schema(type=types.Type.STRING, description="Ülke adı (opsiyonel)."),
                "intent_level": types.Schema(
                    type=types.Type.STRING,
                    description="Niyet seviyesi (opsiyonel).",
                    enum=["DÜŞÜK", "ORTA", "YÜKSEK"],
                ),
                "limit": types.Schema(type=types.Type.INTEGER, description="Maksimum sonuç (varsayılan: 50)."),
            },
            required=["sector"],
        ),
    ),
    types.FunctionDeclaration(
        name="get_high_intent_leads",
        description="Yüksek niyet skoru (min_score ve üzeri) olan şirketleri getir (DB modu).",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "min_score": types.Schema(type=types.Type.INTEGER, description="Minimum niyet skoru 1-10 (varsayılan: 8)."),
                "country":   types.Schema(type=types.Type.STRING, description="Ülke filtresi (opsiyonel)."),
                "limit":     types.Schema(type=types.Type.INTEGER, description="Maksimum sonuç (varsayılan: 20)."),
            },
            required=[],
        ),
    ),
    types.FunctionDeclaration(
        name="get_contacts_for_company",
        description="Belirli bir şirketteki kişileri getir (unique_id ile, DB modu).",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "unique_id": types.Schema(type=types.Type.STRING, description="Şirketin benzersiz kimliği."),
                "seniority": types.Schema(type=types.Type.STRING, description="Kıdem filtresi (opsiyonel)."),
            },
            required=["unique_id"],
        ),
    ),
    types.FunctionDeclaration(
        name="search_companies",
        description="Şirket adında anahtar kelime araması yap (DB modu).",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "query": types.Schema(type=types.Type.STRING, description="Şirket adı veya anahtar kelimesi."),
                "limit": types.Schema(type=types.Type.INTEGER, description="Maksimum sonuç (varsayılan: 30)."),
            },
            required=["query"],
        ),
    ),
]


def get_agent_tools(db_mode: bool) -> list[types.Tool]:
    """Return the tool set for the multi-step agent loop.

    CSV mode: filter_dataframe + common tools.
    DB mode:  semantic layer tools + common tools.
    """
    common = [
        ENRICH_COMPANY_INTENT_TOOL.function_declarations[0],
        _GENERATE_OUTREACH_DRAFT_DECL,
    ]
    mode_decls = _SEMANTIC_DECLS if db_mode else [FILTER_DATAFRAME_TOOL.function_declarations[0]]
    return [types.Tool(function_declarations=common + mode_decls)]
