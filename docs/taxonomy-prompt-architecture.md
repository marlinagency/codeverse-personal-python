# Taksonomi-Ölçekli Tema-Eşleme Prompt Mimarisi (Adım 6)

Modül: `backend/src/codeverse_core/theme_mapping/taxonomy_prompts.py`
Kapsam: 980 taksonomi kavramından **~468 benzersiz kanonik isme** tema token'ı
üretmek (Python 197 + SQL 271; SQL'de 131 lehçe-alias'ı tek isimde birleşir).

## Neden iki faz?

Tek çağrı imkânsız (çıktı limiti), bağımsız çağrılar tema tutarlılığını
öldürür. Çözüm:

**Faz A — tema damıtma (tema başına 1 çağrı).** Serbest metin tema →
`ThemeProfile` (8-15 motif + ton + token dili). Bu profil DONDURULUR ve
sonraki her çağrıya aynen verilir — kategoriler arası tutarlılığın mekanizması
budur: bütün batch'ler aynı motif havuzundan beslenir.

**Faz B — batch eşleme (~40 kavram/çağrı, ~12-13 çağrı).** Her çağrıya:
profil + kavram satırları (`- canonical_name: ipucu`) + **FORBIDDEN listesi**
(önceki batch'lerin ürettiği tüm token'lar). Çakışma, validator'a kalmadan
üretim anında engellenir.

## Kanonik isim = prompt para birimi

Prompt'a `concept_id` değil kanonik isim gider (`upper`, `left_join`).
`MappableConcept.concept_ids` alias grubunu taşır: `UPPER` üç lehçe
sayfasında var → modele 1 satır gider, dönen token orkestratör tarafından
3 concept_id'ye yayılır.

Kanonikleşemeyen kavramlar (öğretici konu sayfaları: "Assign Multiple
Values") bilinçli olarak eşleme DIŞI — bunlar token değil, dokümantasyon
malzemesi. `extract_mappable()` bunları `skipped` olarak ayrı döndürür.

## Adım 9 orkestratörünün sözleşmesi

```python
profile = parse_theme_profile_output(llm(build_theme_profile_messages(theme, lang)), theme)
mappable, skipped = extract_mappable(language)
forbidden: list[str] = []
final: dict[str, str] = {}           # concept_id -> token
for batch in chunk_mappable(mappable):          # kind-gruplu, alfabetik, deterministik
    msgs = build_category_mapping_messages(profile, batch, forbidden)
    result = parse_category_mapping_output(llm(msgs), batch)   # eksik isim -> ValueError -> retry
    # validator (Adım 10) burada devreye girer; hata -> correction_feedback ile retry
    for m in batch:
        for cid in m.concept_ids:
            final[cid] = result.mappings[m.canonical_name]
    forbidden.extend(result.mappings.values())
```

- `parse_category_mapping_output` eksik isimde `ValueError` atar → batch
  `correction_feedback` parametresiyle yeniden denenir (mevcut 31-kavram
  generator'ındaki retry deseniyle aynı).
- Fazla/halüsinasyon isimler sessizce atılır.
- `chunk_mappable` deterministik: aynı girdi → aynı batch'ler (tekrar
  çalıştırma ve test için).

## Prompt kuralları (sistem prompt'unda kodlu)

- Token = tek identifier (Unicode harf/rakam/alt çizgi, rakamla başlamaz).
- Batch içi + FORBIDDEN listesiyle çakışma yasak (case-insensitive).
- Gerçek keyword/builtin adları yasak; token kendi gerçek adından farklı olmalı.
- Aile tutarlılığı: `left_join/right_join/inner_join` ortak kök taşımalı.
- Anlam eşlemesi: eylem yapıya eylemsi, hataya uğursuz, veri döndürene isimsi token.

## Canlı doğrulama (gpt-oss-120b, 2026-07-03)

Tema: "dinozorlari cok seven biri" → motifler: fosil, paleontolog, T-Rex,
kazı, kemik... Batch (10 string metodu) → `find→fosil_bul`,
`encode→kemik_kodla`, `count→fosil_say`, `endswith→jurassic_sona_er` —
tamamı identifier-safe, tema-tutarlı, FORBIDDEN'a saygılı.

## Bilinçli sınırlar

- Bu modül saf prompt inşası + parse; I/O ve orkestrasyon yok (Adım 9'un işi).
- Canlı 31-kavram pipeline'ına (`prompt_templates.py`) dokunulmadı; taksonomi
  sözlüğü canlıya Adım 9-11'de bağlanır.
- 3 SQL kavramı kanonikleşemiyor ("CREATE OR REPLACE VIEW", "Concat with +/&")
  — skipped'a düşer, kayıp kabul edilebilir.
