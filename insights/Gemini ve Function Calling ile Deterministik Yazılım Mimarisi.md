Kullanıcının doğal dildeki karmaşık ve serbest metinli taleplerini (örneğin, *"Bana son 48 saat içinde siber güvenlik bütçesini artıracağını belirten, New York merkezli Seri C fintech şirketlerini bul ve CTO'larına özel taslak oluştur"*) doğrudan çalıştırılabilir koda ve veritabanı sorgularına dönüştüren temel motor **Fonksiyon Çağırma (Function Calling)** yapısıdır 1, 2\.  
Bu yapıda **Büyük Dil Modeli (Gemini) kodun kendisini çalıştırmaz**; bunun yerine hangi kodun, hangi parametrelerle çalıştırılması gerektiğine karar veren bir "karar verici/orkestra şefi" rolü üstlenir 3-5.  
Sisteminizde kullanıcının isteğini koda dönüştüren 4 adımlı standart yaşam döngüsü şu şekilde çalışır:

### 1\. Fonksiyonların Tanımlanması (Function Declarations)

Öncelikle arka planda (Python/LangGraph) AI'ın kullanabileceği "araçları" (tools/functions) tanımlarız 3\. Bu tanımlamalar, Pydantic veya OpenAPI JSON şemaları formatında modelle paylaşılır 6-8. Model bu sayede hangi fonksiyonun ne işe yaradığını ve hangi veri tiplerini (integer, string, enum) kabul ettiğini öğrenir 7, 9\.

* *Örnek Tanımlama:* get\_companies\_by\_sector(sector: str, intent\_level: str, limit: int) \-\> *"Belirtilen sektörde ve niyet seviyesindeki şirketleri getirir."* 10

### 2\. İstem (Prompt) ve Modelin Kararı

Kullanıcı sorusunu sorduğunda, model bu doğal dili analiz eder ve önceden tanımladığımız araçlardan birine veya birkaçına ihtiyaç duyup duymadığına karar verir 3\. Geleneksel serbest metin (text) yerine, arka plana benzersiz bir id'ye sahip yapılandırılmış bir **JSON (FunctionCall)** objesi döndürür 3, 11, 12\.

* *Model Çıktısı:* Fonksiyon: get\_companies\_by\_sector | Argümanlar: {"sector": "fintech", "intent\_level": "YÜKSEK", "limit": 5} 10

### 3\. Lokal Çalıştırma (Sizin Backend'iniz)

Bu adımda kontrol tamamen sizin sisteminize (Python kodunuza) geçer. Sistem, Gemini'den gelen argümanları alır, doğruluk kontrolünden geçirir ve gerçek veritabanı sorgusunu veya dış API isteğini çalıştırır 3, 4, 13\.

* **Güvenlik Bariyeri (Semantic Layer & OCap):** Model doğrudan SQL metni üretmediği için (Text-to-SQL yerine), önceden yazılmış güvenli şablonlarınız (Semantic Layer) çalışır 14-17. Modelin veritabanını silme (DROP/DELETE) veya yetkisiz verilere ulaşma şansı **sıfırdır**, çünkü sadece sizin izin verdiğiniz fonksiyonları yetkilendirildiği kısıtlamalar dahilinde çağırabilir 16, 18-20.

### 4\. Sonucun LLM'e Geri Döndürülmesi (Rehydration/Response)

Python fonksiyonunuz sonucu (Örn: Çekilen 5 firmanın bilgileri) JSON formatında aldıktan sonra, bu sonucu ilk adımdaki eşleşen id ile modele **FunctionResponse** olarak geri gönderir 3, 4, 11\. Model bu veriyi okur ve kullanıcıya sunulacak nihai, sentezlenmiş insan dilindeki cevabı veya kişiselleştirilmiş e-posta taslağını oluşturur 3, 4, 21\.

### Gelişmiş "Function Calling" Mimarisi Avantajları

B2B AI SDR sisteminizin kompleks senaryolarında bu yapının sunduğu gelişmiş yetenekler şunlardır:

* **Sıralı (Sequential) Çok Adımlı Çağrılar:** Kullanıcı karmaşık bir istekte bulunduğunda, Gemini 3.1 modelleri bu işlemleri zincirleyebilir 10, 22\. Örneğin; önce get\_companies fonksiyonunu çağırır, sonucu alır almaz kendi kendine bir sonraki adım olan get\_purchasing\_contacts(company\_ids) fonksiyonunu tetikler 10\. Bu esnada aradaki mantık zincirini kaybetmemek için şifrelenmiş **Düşünme İmzası (Thought Signatures)** kullanır 23-25.  
* **Paralel Fonksiyon Çağırma:** Kullanıcı "Hem sağlık hem de otomotiv sektöründeki şirketleri bul" dediğinde, sistem iki ayrı sektör araması için eşzamanlı (asenkron) ve paralel olarak birden fazla fonksiyon çağrısı üretebilir, bu da API bekleme sürelerinizi yarı yarıya düşürür 26-29.  
* **Davranış Modu Kontrolü (Modes):** İş akışınızın kesinliğine göre modele zorunluluklar getirebilirsiniz. Örneğin doğrudan veritabanı ile konuşan bir arka plan ajanınız varsa, modeli **ANY** veya **VALIDATED** modunda çalıştırarak serbest metin gevezeliği yapmasını engeller ve *kesinlikle* şemaya uygun bir fonksiyon çağırmaya zorlarsınız 25, 30, 31\.

Özetle; Function Calling yapısı sayesinde "Vibe Coding" ile geliştireceğiniz LLM ajanları halüsinasyon gören metin üreticileri olmaktan çıkar ve dış dünyayla güvenli, öngörülebilir bir şekilde etkileşime giren **deterministik yazılım bileşenlerine** dönüşür 32, 33\.  
