Techsalerator veri setinin ("Bones \- Firmographic Data Sample") orijinal yapısını incelediğimizde 1-6, şirketlerin kimlik, lokasyon, sektör, ciro, çalışan sayısı ve üst düzey yönetici (CEO) bilgilerini detaylı bir şekilde barındırdığını görüyoruz.  
Gemini tabanlı B2B AI SDR projeniz için bu statik firma verilerini, otonom web taramalarıyla elde edilecek **sentetik niyet (intent) sinyalleriyle** birleştirmek için hem veritabanında (SQL) hem de LLM arka planında (Pydantic/JSON) kullanabileceğiniz ideal şema yapısı şu şekildedir:

### 1\. SQL Veritabanı Şeması (PostgreSQL / SQLite)

Techsalerator'ın sunduğu statik verileri tutarken, Gemini'nin "Google Arama ile Temellendirme (Grounding)" yeteneğiyle bulacağı dinamik niyet verilerini JSONB formatında saklamak en esnek yöntemdir 7\.  
CREATE TABLE target\_companies (  
    \-- Techsalerator Temel Firma Verileri \[1-6\]  
    unique\_id VARCHAR(50) PRIMARY KEY,        \-- Benzersiz Techsalerator ID (Örn: 612215802\)  
    company\_name VARCHAR(255) NOT NULL,       \-- Firma Adı  
    website VARCHAR(255),                     \-- Web Sitesi (URL)  
    country VARCHAR(50),                      \-- Ülke  
    city VARCHAR(100),                        \-- Şehir  
    industry\_code VARCHAR(50),                \-- Sektör Kodu (PrimaryLocalActivityCode)  
    employees\_total INTEGER,                  \-- Toplam Çalışan Sayısı  
    sales\_volume\_dollars NUMERIC(15,2),       \-- Dolar Cinsinden Ciro Tahmini  
    ceo\_name VARCHAR(255),                    \-- Üst Düzey Yönetici Adı Soyadı  
    contact\_email VARCHAR(255),               \-- İletişim E-postası  
      
    \-- Üretilecek Sentetik Niyet (Intent) Katmanı \[7, 8\]  
    intent\_score INTEGER CHECK (intent\_score \>= 1 AND intent\_score \<= 10), \-- Niyet Puanı (1-10)  
    intent\_level VARCHAR(20) CHECK (intent\_level IN ('DÜŞÜK', 'ORTA', 'YÜKSEK')), \-- Segmentasyon  
    intent\_signals JSONB,                     \-- AI tarafından sentezlenen sinyaller listesi   
    grounding\_urls JSONB,                     \-- Teyit için Google Arama kaynak linkleri  
    last\_intent\_update TIMESTAMP DEFAULT CURRENT\_TIMESTAMP  
);

### 2\. LLM Orkestrasyonu İçin Pydantic (JSON) Şeması

Python ve LangGraph arka planında Gemini API'yi "Yapılandırılmış Çıktılar (Structured Outputs)" modunda çalıştırırken, AI'ın veritabanına yazacağı şemayı bir Pydantic modeli ile tip güvenli (type-safe) hale getirmelisiniz 9, 10\.  
from pydantic import BaseModel, Field  
from typing import List, Optional  
from enum import Enum

\# Enum yapısı, LLM'in uydurma etiketler üretmesini engeller \[11\]  
class IntentLevel(str, Enum):  
    HIGH \= "YÜKSEK" \# 8-10 puan \[8\]  
    MEDIUM \= "ORTA" \# 5-7 puan \[8\]  
    LOW \= "DÜŞÜK"   \# 1-4 puan \[8\]

class CompanyIntentProfile(BaseModel):  
    unique\_id: str \= Field(description="Şirketin veritabanındaki eşsiz ID'si")  
    company\_name: str  
      
    \# AI Analizi Çıktıları  
    intent\_score: int \= Field(ge=1, le=10, description="Web sinyallerine dayalı 1-10 arası niyet puanı")  
    intent\_level: IntentLevel \= Field(description="Niyet skoruna bağlı kategori")  
      
    intent\_signals: List\[str\] \= Field(  
        description="Örn: \['Yeni fabrika yatırımı duyuruldu', 'Siber güvenlik için kıdemli mühendis aranıyor'\]"  
    )  
    grounding\_urls: List\[str\] \= Field(  
        description="Bu sinyallerin tespit edildiği URL kaynakları (Haberler, LinkedIn ilanları vb.)"  
    )

### Şema Tasarımının Stratejik Nedenleri:

* **Puanlama ve Segmentasyon (Intent Score & Level):** İncelediğim kaynaklara göre B2B niyet skoru 1 ile 10 arasında ağırlıklandırılarak bir matrise oturtulmalıdır 8\. Örneğin, "genel sektörel haberler" 1-4 (Düşük) puan alırken, "büyük çaplı ihale veya teknolojik değişim" 8-10 (Yüksek) puan almalıdır 8\. Otonom SDR (Satış Temsilcisi) ajanı, bu "Level" kolonuna bakarak sadece "YÜKSEK" olanlara hemen e-posta taslağı hazırlar.  
* **Kanıt Kaynakları (Grounding URLs):** Gemini, hedef şirket hakkında internette araştırma yaptığında (intent\_signals kolonunu doldururken), kanıt bulduğu web sitelerinin linklerini grounding\_urls kolonuna JSONB dizisi olarak kaydeder 7\. Bu, ajanınızın halüsinasyon görüp görmediğini teyit etmeniz için kritik bir mekanizmadır 7\.  
* **JSONB Formatının Esnekliği:** Hem intent\_signals (örn: "Şirket C serisi yatırım aldı", "X pozisyonu için ilan açtı") hem de grounding\_urls alanlarını SQL veritabanında JSONB olarak tutmak, ileride Streamlit arayüzünde filtreleme yapmanızı (Örn: *İçinde "yatırım" geçen yüksek niyetli firmaları listele*) inanılmaz derecede kolaylaştıracaktır.

