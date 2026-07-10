# AMD Instinct Fine-tune Demo — Runbook

Hackathon'un "AMD platform kullanımı" kriterini karşılayan öğretmen→öğrenci
distilasyon demosu:

- **Öğretmen** (Fireworks, `glm-5p2`): CodeVerse'ün gerçek prompt'larıyla
  yüzlerce doğrulanmış tema-profili + netleştirme-sorusu örneği üretir.
Veri havuzu İngilizce-only'dir (ürün kararı: uygulama tamamen İngilizce).

- **Öğrenci** (Qwen2.5-3B-Instruct): AMD AI Notebook'ta (ROCm + PyTorch)
  LoRA ile fine-tune edilir, **vLLM** ile OpenAI-uyumlu API olarak servis
  edilir ve CodeVerse uygulaması **tek satır config değişikliğiyle** ona
  bağlanır.

Demo cümlesi: *"Tema motorumuz artık AMD Instinct üzerinde, ROCm ile kendi
eğittiğimiz modelle çalışıyor — provider mimarimiz sayesinde tek satırla."*

## Adımlar

### 1. Lokalde: eğitim verisini üret (GPU gerekmez, notebook kotasını yakmaz)

```powershell
# repo kökünden — ~600 örnek, ~15-20 dk, < $5 Fireworks kredisi
.venv\Scripts\python amd\generate_training_data.py --count 600 --workers 8
```

Çıktı: `amd/codeverse_theme_sft.jsonl` — her satır, uygulamanın GERÇEK
parser'larından geçmiş (kalite filtreli) bir chat örneği.

Önce boru hattını denemek için: `--count 8 --out amd/pilot_sft.jsonl`
(pilot koşusu yapıldı: 6/8 geçerli, hatalılar filtre tarafından elendi).

### 2. AMD portalında: notebook başlat

`notebooks.amd.com/hackathon` → image: **ROCm 7.2 + vLLM 0.16.0 + PyTorch 2.9**
→ **Request Notebook**. (Kota: 24 saatte 12 saat — veri üretimi bittikten
sonra başlatın ki GPU saati boşa akmasın.)

### 3. Notebook'ta: yükle ve hücreleri sırayla çalıştır

- `codeverse_finetune_amd.ipynb` + `codeverse_theme_sft.jsonl` dosyalarını
  Jupyter'a yükleyin (aynı klasöre).
- Hücreler sırasıyla: GPU kontrolü → kurulum → veri → **LoRA eğitimi**
  (~600 örnekte tahmini 10-25 dk) → merge → **vLLM servis** → held-out
  **eval** (JSON geçerlilik + gecikme) → **cloudflared tüneli** (public URL
  basar).

### 4. Lokalde: uygulamayı AMD'deki öğrenciye bağla

Son hücrenin bastığı URL ile `.env`:

```
CODEVERSE_LLM_PROVIDER=openai_compatible
CODEVERSE_OPENAI_BASE_URL=https://<tunel>.trycloudflare.com/v1
CODEVERSE_OPENAI_API_KEY=not-needed
CODEVERSE_OPENAI_MODEL=codeverse-student
```

Backend'i yeniden başlatın (`.venv` + `--reload`). Tema üretimi artık AMD
Instinct'te çalışır. Geri dönüş: `CODEVERSE_LLM_PROVIDER=fireworks`.

## Notlar / riskler

- Notebook hücreleri hackathon image'ında test edilmek üzere yazıldı; `trl`
  sürüm farklarında `SFTConfig` alan adları oynayabilir (hata verirse alan
  adını sürümün beklediğiyle değiştirmek yeterli).
- 3B öğrenci, 120B+ öğretmenin kalitesini geçmek için değil; **AMD donanımında
  eğitilmiş + servis edilen, uygulamaya takılabilir** bir uzman model
  göstermek için var. Eval hücresi jüriye ölçüm verir (geçerlilik oranı +
  gecikme).
- Cloudflared quick tunnel hesap gerektirmez ama URL geçicidir — demo
  sırasında notebook açık kalmalı.
- $100 AMD kredisi bu akışta hiç harcanmaz (notebook ücretsiz); kredi,
  gerekirse daha uzun/kalıcı bir GPU droplet için yedekte durur.
