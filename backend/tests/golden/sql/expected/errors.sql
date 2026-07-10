-- === CodeVerse SQL runtime prelude (auto-generated, do not edit) ===
CREATE OR REPLACE FUNCTION _cv_len(j jsonb) RETURNS integer
LANGUAGE sql IMMUTABLE AS $cv$
  SELECT CASE jsonb_typeof(j)
    WHEN 'array'  THEN jsonb_array_length(j)
    WHEN 'object' THEN (SELECT count(*)::int FROM jsonb_object_keys(j))
    WHEN 'string' THEN char_length(j #>> '{}')
    ELSE NULL END
$cv$;

CREATE OR REPLACE FUNCTION _cv_len(t text) RETURNS integer
LANGUAGE sql IMMUTABLE AS $cv$ SELECT char_length(t) $cv$;

CREATE OR REPLACE FUNCTION _cv_append(arr jsonb, v jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $cv$
  SELECT coalesce(arr, '[]'::jsonb) || jsonb_build_array(v)
$cv$;

CREATE OR REPLACE FUNCTION _cv_remove(arr jsonb, v jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $cv$
  WITH elems AS (
    SELECT value, ordinality FROM jsonb_array_elements(arr) WITH ORDINALITY
  ),
  first_match AS (SELECT min(ordinality) AS ord FROM elems WHERE value = v)
  SELECT coalesce(jsonb_agg(value ORDER BY ordinality), '[]'::jsonb)
  FROM elems, first_match
  WHERE first_match.ord IS NULL OR ordinality <> first_match.ord
$cv$;

CREATE OR REPLACE FUNCTION _cv_contains(col jsonb, v jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $cv$
  SELECT CASE jsonb_typeof(col)
    WHEN 'array'  THEN EXISTS (SELECT 1 FROM jsonb_array_elements(col) e WHERE e = v)
    WHEN 'object' THEN col ? (v #>> '{}')
    ELSE false END
$cv$;

CREATE OR REPLACE FUNCTION _cv_get(d jsonb, k jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $cv$
  SELECT CASE jsonb_typeof(d)
    WHEN 'array' THEN d -> ((k #>> '{}')::int)
    ELSE d -> (k #>> '{}') END
$cv$;

CREATE OR REPLACE FUNCTION _cv_set(d jsonb, k jsonb, v jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $cv$
  SELECT jsonb_set(
    coalesce(d, '{}'::jsonb),
    ARRAY[(k #>> '{}')],
    v,
    true
  )
$cv$;

CREATE OR REPLACE FUNCTION _cv_del(d jsonb, k jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $cv$
  SELECT CASE jsonb_typeof(d)
    WHEN 'array' THEN d - ((k #>> '{}')::int)
    ELSE d - (k #>> '{}') END
$cv$;

CREATE OR REPLACE FUNCTION _cv_keys(d jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $cv$
  SELECT coalesce(jsonb_agg(k), '[]'::jsonb) FROM jsonb_object_keys(d) k
$cv$;

CREATE OR REPLACE FUNCTION _cv_values(d jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $cv$
  SELECT coalesce(jsonb_agg(value), '[]'::jsonb) FROM jsonb_each(d)
$cv$;

CREATE OR REPLACE FUNCTION _cv_num(j jsonb) RETURNS numeric
LANGUAGE sql IMMUTABLE AS $cv$ SELECT (j #>> '{}')::numeric $cv$;

CREATE OR REPLACE FUNCTION _cv_str(j jsonb) RETURNS text
LANGUAGE sql IMMUTABLE AS $cv$
  SELECT CASE
    WHEN j IS NULL THEN NULL
    WHEN jsonb_typeof(j) IN ('string') THEN j #>> '{}'
    WHEN jsonb_typeof(j) = 'boolean' THEN CASE WHEN (j #>> '{}')::boolean THEN 'True' ELSE 'False' END
    ELSE j::text END
$cv$;

CREATE OR REPLACE FUNCTION _cv_str_count(t text, needle text) RETURNS integer
LANGUAGE sql IMMUTABLE AS $cv$
  SELECT CASE
    WHEN needle = '' THEN char_length(t) + 1
    ELSE ((char_length(t) - char_length(replace(t, needle, ''))) / char_length(needle))::int
  END
$cv$;

CREATE OR REPLACE FUNCTION _cv_str_rfind(t text, needle text) RETURNS integer
LANGUAGE sql IMMUTABLE AS $cv$
  SELECT CASE
    WHEN strpos(reverse(t), reverse(needle)) = 0 THEN -1
    ELSE char_length(t) - strpos(reverse(t), reverse(needle)) - char_length(needle) + 1
  END
$cv$;

CREATE OR REPLACE FUNCTION _cv_str_join(sep text, arr jsonb) RETURNS text
LANGUAGE sql IMMUTABLE AS $cv$
  SELECT coalesce(string_agg(_cv_str(value), sep ORDER BY ordinality), '')
  FROM jsonb_array_elements(coalesce(arr, '[]'::jsonb)) WITH ORDINALITY
$cv$;

CREATE OR REPLACE FUNCTION _cv_clear(j jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $cv$
  SELECT CASE jsonb_typeof(j)
    WHEN 'object' THEN '{}'::jsonb
    ELSE '[]'::jsonb END
$cv$;

CREATE OR REPLACE FUNCTION _cv_extend(a jsonb, b jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $cv$
  SELECT coalesce(a, '[]'::jsonb) || coalesce(b, '[]'::jsonb)
$cv$;

CREATE OR REPLACE FUNCTION _cv_insert(arr jsonb, idx integer, v jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $cv$
  SELECT jsonb_insert(coalesce(arr, '[]'::jsonb), ARRAY[idx::text], v, false)
$cv$;

CREATE OR REPLACE FUNCTION _cv_reverse(arr jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $cv$
  SELECT coalesce(jsonb_agg(value ORDER BY ordinality DESC), '[]'::jsonb)
  FROM jsonb_array_elements(coalesce(arr, '[]'::jsonb)) WITH ORDINALITY
$cv$;

CREATE OR REPLACE FUNCTION _cv_sort(arr jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $cv$
  SELECT coalesce(jsonb_agg(value ORDER BY value #>> '{}'), '[]'::jsonb)
  FROM jsonb_array_elements(coalesce(arr, '[]'::jsonb)) value
$cv$;

CREATE OR REPLACE FUNCTION _cv_update(d jsonb, other jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $cv$
  SELECT coalesce(d, '{}'::jsonb) || coalesce(other, '{}'::jsonb)
$cv$;

CREATE OR REPLACE FUNCTION _cv_items(d jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $cv$
  SELECT coalesce(jsonb_agg(jsonb_build_array(key, value) ORDER BY key), '[]'::jsonb)
  FROM jsonb_each(coalesce(d, '{}'::jsonb))
$cv$;
-- === end prelude ===

CREATE OR REPLACE FUNCTION guvenli_bolme(a numeric, b numeric)
RETURNS numeric
LANGUAGE plpgsql AS $fn$
DECLARE
  hata text;
BEGIN
  BEGIN
    RETURN (a / b);
  EXCEPTION WHEN OTHERS THEN
    hata := SQLERRM;
    RAISE NOTICE '%', coalesce('hata yakalandi', 'None');
    RETURN NULL;
  END;
END
$fn$;

DO $main$
DECLARE
  sayac numeric;
  toplam numeric;
BEGIN
  RAISE NOTICE '%', coalesce((guvenli_bolme(10, 2))::text, 'None');
  RAISE NOTICE '%', coalesce((guvenli_bolme(1, 0))::text, 'None');
  sayac := 0;
  WHILE true LOOP
    sayac := (sayac + 1);
    IF (sayac >= 3) THEN
      EXIT;
    END IF;
  END LOOP;
  RAISE NOTICE '%', coalesce((sayac)::text, 'None');
  toplam := 0;
  FOR i IN (1)::int..((6)::int) - 1 LOOP
    IF ((i % 2) = 0) THEN
      CONTINUE;
    END IF;
    toplam := (toplam + i);
  END LOOP;
  RAISE NOTICE '%', coalesce((toplam)::text, 'None');
END
$main$;