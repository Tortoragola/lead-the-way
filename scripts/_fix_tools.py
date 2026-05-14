"""One-shot script to rewrite FILTER_DATAFRAME_TOOL with correct UTF-8 text."""
import pathlib

tools_path = pathlib.Path(__file__).parent.parent / "ltw" / "llm" / "tools.py"

with open(tools_path, "r", encoding="utf-8-sig") as f:
    content = f.read()

start = content.index("FILTER_DATAFRAME_TOOL = types.Tool(")
end   = content.index("\n\n\nENRICH_COMPANY_INTENT_TOOL")

new_block = (
    'FILTER_DATAFRAME_TOOL = types.Tool(\n'
    '    function_declarations=[\n'
    '        types.FunctionDeclaration(\n'
    '            name="filter_dataframe",\n'
    '            description=(\n'
    '                "B2B iletişim veritabanını verilen kriterlere göre filtreler. "\n'
    '                "Kullanıcının doğal dildeki isteğini sütun bazlı filtre kurallarına dönüştür."\n'
    '            ),\n'
    '            parameters=types.Schema(\n'
    '                type=types.Type.OBJECT,\n'
    '                properties={\n'
    '                    "filters": types.Schema(\n'
    '                        type=types.Type.ARRAY,\n'
    '                        description="Uygulanacak filtre kuralları listesi",\n'
    '                        items=types.Schema(\n'
    '                            type=types.Type.OBJECT,\n'
    '                            properties={\n'
    '                                "column": types.Schema(\n'
    '                                    type=types.Type.STRING,\n'
    '                                    description=(\n'
    '                                        "Filtrelenecek sütun adı. Geçerli değerler: "\n'
    '                                        "First Name, Last Name, Title, Company Name, Email, "\n'
    '                                        "Seniority, Departments, Sub Departments, Industry, "\n'
    '                                        "City, State, Country, Company City, Company Country, "\n'
    '                                        "# Employees, Annual Revenue, Technologies, Keywords"\n'
    '                                    ),\n'
    '                                ),\n'
    '                                "operator": types.Schema(\n'
    '                                    type=types.Type.STRING,\n'
    '                                    description=(\n'
    '                                        "Filtre operatörü. "\n'
    '                                        "KURAL: Title, Departments, Industry, Technologies, Keywords için "\n'
    '                                        "DAIMA `contains` kullan \u2014 asla `equals` değil (değerler birleşik olabilir). "\n'
    '                                        "Country, Seniority için `equals` veya `in_list` kullanabilirsin. "\n'
    '                                        "Sayısal karşılaştırmalar için `greater_than` / `less_than`."\n'
    '                                    ),\n'
    '                                    enum=[\n'
    '                                        "contains", "not_contains", "equals", "not_equals",\n'
    '                                        "starts_with", "ends_with", "greater_than", "less_than",\n'
    '                                        "in_list",\n'
    '                                    ],\n'
    '                                ),\n'
    '                                "value": types.Schema(\n'
    '                                    type=types.Type.STRING,\n'
    '                                    description=(\n'
    '                                        "Filtre değeri. in_list için virgülle ayrılmış değerler. "\n'
    '                                        "Türkçe terimler İngilizce karşılıklarıyla eşleştirilir "\n'
    '                                        "(örn. \'pazarlama\' \u2192 \'marketing\', \'müdür\' \u2192 \'manager\'). "\n'
    '                                        "Unvan+departman kombinasyonunda tam ifade kullan: "\n'
    '                                        "örn. \'Marketing Manager\' (\'Manager\' + ayrı \'Marketing\' değil)."\n'
    '                                    ),\n'
    '                                ),\n'
    '                            },\n'
    '                            required=["column", "operator", "value"],\n'
    '                        ),\n'
    '                    ),\n'
    '                    "logic": types.Schema(\n'
    '                        type=types.Type.STRING,\n'
    '                        description=(\n'
    '                            "Filtreler arası mantık operatörü. "\n'
    '                            "Hem Title hem Departments filtreliyorsan OR kullan; "\n'
    '                            "bağımsız kriterler için (Country + Seniority gibi) AND kullan."\n'
    '                        ),\n'
    '                        enum=["AND", "OR"],\n'
    '                    ),\n'
    '                },\n'
    '                required=["filters"],\n'
    '            ),\n'
    '        )\n'
    '    ]\n'
    ')'
)

new_content = content[:start] + new_block + content[end:]

with open(tools_path, "w", encoding="utf-8") as f:
    f.write(new_content)

print("tools.py FILTER_DATAFRAME_TOOL rewritten OK")

# Verify
with open(tools_path, "r", encoding="utf-8") as f:
    check = f.read()
assert "iletişim" in check, "Turkish chars missing!"
assert "`contains` kullan" in check, "Operator guidance missing!"
print("Verification passed.")
