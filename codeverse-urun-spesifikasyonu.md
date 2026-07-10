# CodeVerse (Çalışma Adı) — Tam Sistem Ürün Spesifikasyonu

## AMD Developer Hackathon: ACT II — Track 3: Unicorn Track

---

## 1. Ürün Vizyonu

Kullanıcının seçtiği herhangi bir ilgi alanı/tema ile, seçtiği herhangi bir programlama dilini birleştiren, kişiselleştirilmiş bir syntax katmanı üreten ve bunu gerçek, çalışan koda dönüştüren uçtan uca bir geliştirme platformu. Kullanıcı, desteklenen dil listesinden istediğini seçiyor; sistem o dilin tüm söz dizimini, kullanıcının temasına göre yeniden adlandırıyor ve production-kalite bir geliştirme ortamı (VS Code eklentisi) üzerinden gerçek zamanlı çalıştırıyor.

---

## 2. Desteklenen Diller (Seçim Listesi)

Kullanıcı arayüzünde açılır bir liste olarak sunulacak diller:

- SQL
- Python
- JavaScript
- TypeScript
- C++
- Java
- Go
- Rust (opsiyonel genişleme)

Her dil, sistemin ortak mimarisi üzerinden aynı pipeline'dan geçiyor — dil bazlı özel kod tabanı değil, **tek bir merkezi motor + dile özel eklenti modülleri** yapısı.

---

## 3. Sistem Mimarisi

```
┌─────────────────────────────────────────────────────────────┐
│                     KULLANICI ARAYÜZÜ                         │
│           (VS Code Eklentisi + Web Dashboard)                 │
└───────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                  TEMA-KAVRAM EŞLEME KATMANI                   │
│        (Fireworks AI üzerinden, dilden bağımsız çalışır)      │
│                                                                 │
│  Girdi: Kullanıcı teması + Evrensel Kavram Listesi             │
│  Çıktı: Tutarlı, tema-özel anahtar kelime/syntax sözlüğü       │
└───────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                 EVRENSEL AYRIŞTIRMA KATMANI                   │
│           (Universal Abstract Syntax Layer - UASL)             │
│                                                                 │
│  Her dilin ortak yapı taşlarını (fonksiyon, döngü, koşul,      │
│  değişken, sınıf, import) soyut bir ara temsile çeviriyor       │
└───────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│              DİLE ÖZEL ÜRETİM MODÜLLERİ (Codegen)              │
│                                                                 │
│  [SQL Modülü] [Python Modülü] [JS Modülü] [C++ Modülü] ...    │
│  Her modül, UASL'den kendi hedef dilinin gerçek, çalışan        │
│  kodunu üretir                                                  │
└───────────────────────────┬─────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                    ÇALIŞTIRMA / DOĞRULAMA                     │
│                                                                 │
│  Sandbox execution engine + syntax/tip kontrolü +               │
│  hata ayıklama ve zengin hata mesajları                        │
└─────────────────────────────────────────────────────────────┘
```

### 3.1. Tema-Kavram Eşleme Katmanı

- Her programlama dili için ortak bir **Evrensel Kavram Listesi** tanımlanıyor: fonksiyon tanımlama, değer döndürme, koşul, döngü (for/while), sınıf/nesne tanımlama, değişken atama, kütüphane/modül dahil etme, hata yakalama (try/catch), liste/dizi işlemleri, sözlük/harita işlemleri.
- Kullanıcı temasını girdiğinde (örnek: "Valorant"), bu liste Fireworks AI'ya gönderiliyor, her kavram için temaya uygun, birbiriyle tutarlı bir kelime/ifade üretiliyor.
- Üretilen eşleme JSON formatında saklanıyor, kullanıcı profiline bağlı kalıcı bir "kişisel dil sözlüğü" oluşturuyor.

### 3.2. Evrensel Ayrıştırma Katmanı (UASL)

- Kullanıcının, kişisel syntax'ıyla yazdığı kod önce tema sözlüğü üzerinden **gerçek anahtar kelimelere geri çözülüyor**.
- Ardından, hedef dilden bağımsız bir soyut söz dizim ağacı (Abstract Syntax Tree benzeri yapı) oluşturuluyor.
- Bu katman, yeni bir hedef dil eklenmesini kolaylaştıran temel tasarım kararı — yeni dil eklemek, bu katmana yeni bir "çıktı üretici" (codegen) modülü eklemek anlamına geliyor, tüm sistemi yeniden yazmak değil.

### 3.3. Dile Özel Üretim Modülleri

Her desteklenen dil için ayrı bir codegen modülü bulunuyor. Bu modüller:
- UASL'den gelen soyut yapıyı, hedef dilin gerçek, derlenebilir/çalıştırılabilir söz dizimine çeviriyor.
- Dile özel kurallara uyuyor (örnek: Python'da girinti/indentation önemli, C++'ta noktalı virgül ve tip tanımları zorunlu, SQL'de büyük/küçük harf duyarlılığı farklı).
- Her modül bağımsız test edilebiliyor, bu da kalite kontrolünü kolaylaştırıyor.

### 3.4. Çalıştırma ve Doğrulama Katmanı

- Üretilen kod, izole bir sandbox ortamında çalıştırılıyor (Docker container tabanlı, dil bazlı runtime image'ları).
- Hata durumunda, kullanıcının kendi temasına uygun, anlaşılır hata mesajları üretiliyor (örnek: eksik `WHERE` koşulu olan bir SQL sorgusunda, Valorant temasında "site belirtilmeden işlem yapılamaz" gibi).
- Tip kontrolü ve syntax doğrulama, gerçek zamanlı olarak VS Code eklentisinde gösteriliyor.

---

## 4. Geliştirme Ortamı Entegrasyonu (VS Code Eklentisi)

- Özel dosya uzantısı tanımlanıyor (örnek: `.cvl`), her dosyanın başında hangi tema + hangi hedef dil kullanıldığı belirtiliyor.
- **Syntax Highlighting:** TextMate Grammar ile kullanıcının kişisel syntax'ı renklendiriliyor.
- **Gerçek Zamanlı Tanılama (Diagnostics):** VS Code'un Diagnostic API'si üzerinden, hatalı satırlar kırmızı alt çizgiyle işaretleniyor, "Problems" panelinde detaylı açıklama gösteriliyor.
- **Çalıştırma Komutu:** Kullanıcı `Run` komutuyla dosyayı çalıştırıyor, sonuç entegre bir panelde (Output/Terminal) gösteriliyor.
- **Çeviri Paneli:** İsteğe bağlı olarak, kullanıcının yazdığı her satırın gerçek dil karşılığı yan panelde gösterilebiliyor — öğrenme amaçlı kullanıcılar için.
- **Profesyonel Mod:** İleri seviye kullanıcılar için çeviri panelini kapatıp, sadece kişisel syntax ile tam üretkenlik odaklı çalışma modu.

---

## 5. Teknoloji Yığını

| Katman | Teknoloji |
|---|---|
| Tema-Kavram Eşleme | Fireworks AI API (LLM çağrıları) |
| Backend / API | FastAPI (Python) |
| Ayrıştırma Motoru | Özel yazılmış tokenizer/parser (Python, ANTLR veya benzeri parser generator ile desteklenebilir) |
| Codegen Modülleri | Dil başına ayrı modül (Python paketi olarak organize) |
| Çalıştırma Ortamı | Docker tabanlı sandbox, dil bazlı runtime image'ları |
| VS Code Eklentisi | TypeScript, VS Code Extension API |
| Veritabanı | PostgreSQL (kullanıcı profilleri, tema sözlükleri, proje geçmişi) |
| Altyapı | AMD Developer Cloud (GPU gerektiren yoğun işlemler için — örnek: kullanıcı verisiyle ince ayar) |

---

## 6. AMD / Fireworks AI Kullanımı

- **Fireworks AI:** Tema-kavram eşleme üretimi için birincil LLM çağrı noktası. Kullanıcı sayısı arttıkça, üretilen eşlemelerin kalitesini ve tutarlılığını artırmak için prompt mühendisliği ve örnek-tabanlı (few-shot) iyileştirme uygulanıyor.
- **AMD Developer Cloud:** Sistem büyüdükçe, popüler temalar için önceden üretilmiş, kalite kontrolünden geçmiş eşleme veri setleri üzerinde küçük bir modelin ince ayarını (fine-tuning) yapmak için kullanılabiliyor — bu, her kullanıcı için sıfırdan LLM çağrısı yapmak yerine, sık kullanılan temalarda daha hızlı ve tutarlı sonuç üretmeyi sağlıyor.
- **ROCm:** İnce ayar ve olası yerel model çalıştırma senaryolarında GPU hızlandırması için kullanılıyor.

---

## 7. Gelişim Yol Haritası (Aşamalı Kapsam Genişletme)

Sistem mimarisi tüm diller için genişletilebilir şekilde tasarlanmıştır. Codegen modülleri bağımsız birimler olduğundan, yeni bir dil eklemek mevcut sistemi bozmadan gerçekleştirilebiliyor.

| Aşama | Kapsam |
|---|---|
| Faz 1 | Çekirdek mimari (Tema-Kavram Katmanı + UASL) kuruluyor |
| Faz 2 | SQL ve Python modülleri tam derinlikte tamamlanıyor, kapsamlı test edilip production-kalite hâle getiriliyor |
| Faz 3 | JavaScript ve TypeScript modülleri ekleniyor, mimarinin genişletilebilirliği kanıtlanıyor |
| Faz 4 | C++, Java, Go modülleri, kullanıcı talebine ve geri bildirime göre önceliklendirilerek ekleniyor |

---

## 8. Hedef Kullanıcı Kitlesi

- Kodlamaya yeni başlayan öğrenciler (motivasyon ve ezber engelini aşmak için)
- Bootcamp/online eğitim platformları (kurumsal entegrasyon potansiyeli)
- Farklı ilgi alanlarına sahip yetişkin öğrenciler (kariyer değişimi yapanlar)
- İleri düzey geliştiriciler (kişiselleştirilmiş, üretkenlik odaklı kodlama deneyimi isteyenler)

---

## 9. İş Modeli Potansiyeli

- Bireysel kullanıcılar için freemium model (sınırlı tema/dil kombinasyonu ücretsiz, tam erişim ücretli abonelik)
- Eğitim kurumları ve bootcamp'ler için kurumsal lisanslama
- Şirket içi eğitim programları için B2B entegrasyon (örnek: yeni işe başlayan geliştiricilerin şirketin kod tabanına daha hızlı adapte olması)

---

## 10. Track 3 Değerlendirme Kriterlerine Uygunluk

| Kriter | Karşılık |
|---|---|
| Yaratıcılık/Orijinallik | Kişiye özel, AI ile üretilen syntax katmanı — mevcut basitleştirilmiş kodlama araçlarından (Scratch, CodeCombat) farklı, dinamik ve sınırsız tema desteği |
| Ürün/Pazar Potansiyeli | Kodlama eğitimi pazarı büyük ve kanıtlanmış; hem bireysel hem kurumsal satış kanalı mevcut |
| Tamamlanmışlık | Çekirdek mimari + en az iki dilde tam, production-kalite destek ile gerçek, çalışan bir sistem gösteriliyor |
| AMD Platform Kullanımı | Fireworks AI (tema üretimi) + AMD Developer Cloud (ince ayar/ölçeklenebilirlik) anlamlı şekilde entegre |
