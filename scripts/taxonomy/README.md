# CodeVerse Taksonomi (Adım 3 çıktısı)

`taxonomy_python.json` (555 concept) ve `taxonomy_sql.json` (425 concept) —
W3Schools Python/SQL eğitim + referans sayfalarından çıkarılan, temizlenmiş ve
kategorize edilmiş dil kavramları. Toplam **980 benzersiz concept**.

Bu dosyalar `build_taxonomy.py` tarafından `w3schools/output/ham_*_menu.json`
ham taramasından üretilir (yeniden çalıştırılabilir).

## Concept şeması

```json
{
  "concept_id": "py_str_upper",       // benzersiz, kararlı kimlik
  "language": "python",
  "category": "string_methods",
  "tier": "method",
  "title": "upper()",
  "real_syntax": "string.upper()",    // kanonik imza / en iyi mevcut
  "code_examples": [ "..." ],          // sayfadaki TÜM çalışan kod blokları
  "source_url": "https://www.w3schools.com/python/ref_string_upper.asp",
  "description": null                  // Adım 4'te ORİJİNAL cümleyle doldurulacak
}
```

`description` bilinçli olarak `null` — telif sınırı (Adım 0) gereği açıklamalar
W3Schools'tan kopyalanmaz, Adım 4'te kendi cümlelerimizle üretilir.
`code_examples` ham referans malzemesidir; kullanıcıya birebir sunulmaz.

## `tier` — kavramın pipeline'daki rolü

Bu, Adım 3'ün en önemli mimari kararı. Her kavram, tema-eşleme + codegen
hattında nasıl davranacağını belirten bir tier taşır:

| tier | anlam | codegen davranışı |
|---|---|---|
| `core` | dilin anahtar kelimesi / operatörü / ifadesi | temalı token → gerçek UASL yapısı, sandbox'ta çalışır |
| `builtin` | global çağrılabilir isim (`print`, `len`, `COUNT`) | isim olarak temalanır |
| `method` | yerleşik tip metodu (`str.upper`, `list.append`) | isim olarak temalanır |
| `type` | veri tipi adı (`int`, `VARCHAR`) | isim olarak temalanır |
| `exception` | hata/istisna adı | isim olarak temalanır |
| `library` | 3. parti / lehçeye özel yapı (matplotlib, mysql-connector, MySQL-only fonksiyonlar) | **isim olarak** temalanır ama sandbox'ta hatasız çalışması GARANTİ DEĞİL |

`library` tier'ı dürüstlük için var: kullanıcı "her şeyi temala" istiyor, ama
`matplotlib.pyplot` ya da MySQL-only `SYSDATE()` gibi yapılar çekirdek dilin
parçası değil — bunları taksonomiye dahil ediyoruz (eksiksizlik) ama validator/
codegen'in "bu tema-token'ı sandbox'ta çalıştırılamaz, sadece isim değişimi"
kararını verebilmesi için ayrı işaretliyoruz.

## Kategoriler

**Python (27):** builtin_functions, string_methods, list_methods, dict_methods,
set_methods, tuple_methods, file_methods, keywords, exceptions, oop, functions,
control_flow, error_handling, modules, file_io, data_structures, strings, types,
operators, variables, basics + library kategorileri (lib_datascience,
lib_matplotlib, lib_mysql, lib_mongodb, dsa, recipes).

**SQL (14):** query_basics, filtering, joins, aggregation, data_modification,
table_ddl, constraints, indexes_views, database_ddl, conditional, subqueries,
procedures, keywords_misc + string_numeric_functions (lehçeye özel, tier=library).

Not: Plandaki "16+16" hedefi, var olmayan bir önceki taksonomi dosyasına
atıftı; kategori yapısı ham verinin gerçek içeriğinden tasarlandı. Sayı
16'dan farklı çünkü ayrı metod-tipi kategorileri (string/list/dict/set/tuple/
file methods) yapay olarak birleştirmek yerine anlamlı ayrımlar korundu.

## concept_id şeması

`{dil}_{alan}_{ad}`:
- `py_kw_for`, `py_fn_print`, `py_str_upper`, `py_list_append`, `py_exc_valueerror`
- `sql_kw_left_join`, `sql_query_basics_select`, `sql_mysql_concat`

Aynı kavramın iki W3Schools sayfasında geçmesi (ör. INNER JOIN hem tutorial
hem referans sayfasında) çakışma sayılmaz — her ikisi de farklı kod örnekleri
taşıdığı için ayrı id'lerle (`sql_joins_inner_join` / `sql_kw_inner_join`)
korunur.

## Yeniden üretim

```bash
python build_taxonomy.py                    # ham_*_menu.json -> taxonomy_*.json
python fill_taxonomy_descriptions.py        # taxonomy_*.json -> description dolu
python fill_taxonomy_descriptions.py --check
python build_taxonomy.py --input-dir ... --output-dir ...
```

## Adim 4 aciklama uretimi

`description` alanlari `scripts/fill_taxonomy_descriptions.py` ile doldurulur.
Bu script W3Schools aciklama metinlerini okumaz; yalnizca Adim 3 metadata'sini
(`concept_id`, `language`, `category`, `tier`, `title`, `real_syntax`) kullanarak
kisa, ozgun ve telif-guvenli cumleler yazar. `library` tier'indaki kavramlar
ozellikle "sandbox support depends..." ifadesiyle isaretlenir, boylece sonraki
validator/codegen katmanlari bu kavramlarin calisma garantisi olmadigini bilir.
