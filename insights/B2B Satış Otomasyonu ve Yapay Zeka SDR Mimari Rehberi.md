B2B AI SDR ve Lead Generation projeniz için kaynaklarda detaylı bir şekilde analiz edilen, ölçeklenebilir, güvenli ve "Vibe Coding" yaklaşımına uygun mimari yapı şu şekildedir:  
**1\. Frontend (Kullanıcı Arayüzü): Streamlit**Streamlit, özellikle yapay zeka uygulamaları için anında görsel geri bildirim sunan ve hızlı prototiplemeye olanak tanıyan ideal bir arayüz çerçevesidir 1, 2\. Projenizi modüler ve performanslı tutmak için şu yapıları kullanmalısınız:

* **Modüler Mimari:** Tüm kodları tek bir dosyaya yığmak yerine utils/ veya anlamsal klasörler (ör. data/, llm/) oluşturarak API çağrılarını, şablonları ve RAG iş akışlarını ayırmalısınız 3\.  
* **Durum Yönetimi (State Management):** Çok adımlı niyet analizi (intent analysis) süreçlerinde bağlamın kaybolmaması için Streamlit'in st.session\_state yapısını bir durum makinesi (state machine) gibi kullanmalısınız 4, 5\. Bu, internet kopsa bile sürecin kaldığı yerden devam etmesini sağlar 6\.  
* **Maliyet ve Hız Optimizasyonu:** Google Arama gibi dış API maliyetlerini düşürmek ve uygulamayı hızlandırmak için @st.cache\_data dekoratörünü kullanmalısınız 6, 7\.

**2\. Backend & Orkestrasyon: Python \+ LangGraph \+ Gemini API**Otonom satış temsilcinizin arka planında, gelişmiş bir çoklu ajan (multi-agent) mimarisi kurgulamanız gerekir:

* **Çoklu Ajan Orkestrasyonu:** streamlit-langgraph kütüphanesini kullanarak LangGraph'ın esnekliğini Streamlit'e entegre edebilirsiniz 8, 9\. Karmaşık görevleri bölmek için bir yöneticinin (Supervisor) işçi ajanları koordine ettiği "Supervisor Pattern" veya hiyerarşik yapıları kullanabilirsiniz 10\.  
* **LLM Modelleri:** Maliyet ve performans dengesi için karmaşık niyet analizleri ve stratejik karar alma süreçlerinde **Gemini 3.1 Pro**; SQL üretimi (Text-to-SQL) ve düşük gecikme gerektiren veri çıkarma işlemlerinde ise **Gemini 3.1 Flash** kullanmalısınız 11\.  
* **Yapılandırılmış Çıktılar (Structured Outputs):** Geleneksel serbest metin yerine, Pydantic kütüphanesi kullanarak LLM'in üreteceği çıktıları tip güvenli (type-safe) JSON şemalarına zorlamalısınız 12, 13\. Böylece "satın almacı profili" verileri ayrıştırma hatası olmadan doğrudan CRM sistemlerine iletilebilir 12, 14\.  
* **Niyet Sinyali Sentezleme:** Hedef şirketlerle ilgili güncel haberler ve açık pozisyonlar gibi veriler için, modelin canlı web taraması yapabilmesini sağlayan **Google Search Grounding (Temellendirme)** kullanmalısınız 15\.

**3\. Veritabanı (Database): PostgreSQL/SQLite & Anlamsal Katman (Semantic Layer)**LLM'lerin veritabanlarıyla doğrudan etkileşimi yüksek risk taşır ve halüsinasyonlara yatkındır. Bu nedenle şu mimari tercih edilmelidir:

* **Sıfır Güven ve İzolasyon (Zero Trust):** AI ajanı üretim (production) veritabanına asla doğrudan yazma yetkisiyle bağlanmamalıdır. Bunun yerine fiziksel olarak izole edilmiş, asenkron beslenen bir **"Read-Only Replica" (Salt Okunur Kopya)** ile etkileşime girmelidir 16-18.  
* **SQL Güvenliği:** Pydantic-AI tabanlı ajanlarınız için SQLite veya PostgreSQL destekleyen database-pydantic-ai gibi araç kitleri kullanabilir; DELETE, DROP gibi yıkıcı SQL komutlarını bloke eden kısıtlamalar ve zaman aşımı (timeout) kuralları getirebilirsiniz 19, 20\.  
* **Anlamsal Katman (Semantic Layer):** Doğrudan Text-to-SQL kullanmak yerine araya (örneğin dbt gibi) bir Anlamsal Katman koymalısınız. Ajan ham veritabanı tablolarını görmek yerine, "müşteri\_sayısı" gibi önceden tanımlanmış iş metriklerini sorgular 21-23. Bu, SQL halüsinasyonlarını engeller ve doğruluk oranını %100'e kadar çıkarabilir 23, 24\.

**4\. Güvenlik ve KVKK Uyumu (B2B Outreach İçin Kritik)**Cold outreach süreçlerinizin ETK ve KVKK'ya tam uyumlu çalışması için araya bir "AI Gateway" katmanı kurmalısınız 25, 26:

* **In-flight PII Masking (Uçuş Esnasında Maskeleme):** Müşteri verileri, e-posta ve şirket isimleri bulut modeline gönderilmeden önce (ör. Microsoft Presidio kullanarak) yerel ağda maskelenmeli (Tokenization) ve sadece yer tutucular EMAIL\_1 şeklinde LLM'e iletilmelidir. İşlem bitince yanıt orijinal haline döndürülür (Rehydration) 27, 28\.  
* **Guardrails:** Modele sızma girişimlerini (Prompt Injection) durdurmak için model ile sistem arasında bir sınır çizen NVIDIA NeMo Guardrails veya LLM Guard gibi araçlar kullanmalısınız 29, 30\.

