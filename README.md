# 🎯 Lead The Way — AI B2B SDR Platform

Doğal dil komutlarıyla B2B iletişim veritabanlarını filtreleyen ve seçilen kişilere Gemini AI ile kişiselleştirilmiş soğuk satış maili taslakları oluşturan AI-native satış zekası uygulaması.

---

## 🚀 Özellikler

- **Doğal Dil Filtreleme** — "İstanbul'daki fintech şirketlerinin CTO'larını bul" gibi Türkçe/İngilizce komutlarla CSV veritabanını anlık sorgula.
- **Gemini Function Calling** — Kullanıcı sorgusunu `filter_dataframe` fonksiyon çağrısına dönüştürerek tip-güvenli, hatasız filtreleme yapar.
- **Sentetik Satın Alma Niyeti** — Seçilen kişi için şirkete özgü, gerçekçi bir "Intent" cümlesi üretir.
- **Soğuk Satış Maili Taslağı** — Niyet verisini kullanarak kişiye özel, ikna edici bir İngilizce cold outreach maili oluşturur.
- **CSV İndir** — Filtrelenmiş lead listesini ve üretilen mail taslağını dosyaya kaydet.

---

## 📁 Proje Yapısı

```
Lead The Way/
├── app.py                                          # Ana Streamlit uygulaması
├── requirements.txt                                # Python bağımlılıkları
├── Bones - People Inside Businesses Data Sample.csv   # Kişi bazlı B2B verisi
├── Bones - Firmographic Data Sample - Sample_Records.csv
├── Bones - Firmographic Data Sample - International_Categories.csv
├── Bones - Firmographic Data Sample - Fields_Descriptions.csv
├── apollo scrapeleri.csv                           # Apollo'dan dışa aktarılan lead verisi
└── _rtf2csv.py                                     # RTF → CSV dönüştürücü (yardımcı script)
```

---

## ⚙️ Kurulum

### Gereksinimler

- Python 3.10+
- [Gemini API Anahtarı](https://aistudio.google.com/app/apikey) (ücretsiz)

### 1. Depoyu klonla

```bash
git clone https://github.com/Tortoragola/lead-the-way.git
cd lead-the-way
```

### 2. Bağımlılıkları yükle

```bash
pip install -r requirements.txt
```

### 3. Uygulamayı başlat

```bash
streamlit run app.py
```

Tarayıcı otomatik açılır → `http://localhost:8501`

---

## 🔑 Kullanım

1. Sol panelden **Gemini API Anahtarı**nı girin.
2. Arama çubuğuna doğal dilde komut yazın:
   - `Türkiye'deki pazarlama müdürlerini bul`
   - `Bankacılık sektöründeki kıdemli veri bilimciler`
   - `1000'den fazla çalışanı olan teknoloji şirketlerindeki CTO'lar`
3. **Filtrele** butonuna basın — Gemini filtreyi otomatik oluşturur.
4. Sonuç tablosundan bir kişi seçin.
5. **Intent + Mail Taslağı Oluştur** butonuna basın.
6. Üretilen niyet cümlesini ve mail taslağını görüntüleyin veya `.txt` olarak indirin.

---

## 🛠️ Yapılandırma

`app.py` içindeki `PRODUCT_DESCRIPTION` sabitini kendi ürününüzle güncelleyin:

```python
PRODUCT_DESCRIPTION = (
    "Lead The Way: Şirketlerin doğal dil komutlarıyla B2B iletişim "
    "veritabanlarını anlık filtreleyip, yapay zeka destekli kişiselleştirilmiş "
    "soğuk satış mesajları oluşturmasını sağlayan AI-native satış zekası platformu."
)
```

---

## 🧱 Teknoloji Yığını

| Katman | Araç |
|---|---|
| Arayüz | [Streamlit](https://streamlit.io) |
| AI | [Google Gemini 2.0 Flash](https://aistudio.google.com) |
| AI SDK | `google-genai` (Function Calling + JSON mode) |
| Veri | Pandas |

---

## 📄 Lisans

MIT
