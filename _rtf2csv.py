import re, json, pandas as pd
from striprtf.striprtf import rtf_to_text

raw = open(
    r'C:\Users\Tolga\OneDrive\Masaüstü\Lead The Way\apollo scrapeleri.rtf',
    encoding='utf-8', errors='ignore'
).read()

# Use striprtf for proper RTF → plain text conversion (handles cp1254 encoding)
text = rtf_to_text(raw, encoding='cp1254')

# Find the JSON array
match = re.search(r'\[.*\]', text, re.DOTALL)
if not match:
    print('JSON bulunamadı')
    exit(1)

json_text = match.group(0)

# Fix any stray double-backslashes before non-JSON-special characters
json_text = re.sub(r'\\\\(?!["\\/bfnrtu])', ' ', json_text)

try:
    data = json.loads(json_text)
except json.JSONDecodeError as e:
    pos = e.pos
    print(f'JSON hatası: {e}')
    print(f'Bağlam: ...{repr(json_text[max(0, pos-80):pos+80])}...')
    exit(1)


def flatten(v):
    if isinstance(v, list):
        return ', '.join(str(x) for x in v)
    return v


rows = [{k: flatten(v) for k, v in rec.items()} for rec in data]
df = pd.DataFrame(rows)
out = r'C:\Users\Tolga\OneDrive\Masaüstü\Lead The Way\apollo scrapeleri.csv'
df.to_csv(out, index=False, encoding='utf-8-sig')
print(f'Yazıldı: {out}  ({len(df)} satır, {len(df.columns)} sütun)')
