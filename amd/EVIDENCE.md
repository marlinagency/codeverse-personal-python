# AMD fine-tune: verifiable evidence

Screenshots are easy to fake. These artifacts and correlated live logs are
designed to be independently checked.

## 1. Training dataset

`codeverse_theme_sft.jsonl` contains 569 real chat transcripts: 545 training
examples and 24 held-out examples. The teacher was Fireworks `glm-5p2`; every
record was parsed and validated by CodeVerse before it was retained. The AMD
notebook consumes this exact file for the LoRA run.

```bash
wc -l amd/codeverse_theme_sft.jsonl
```

## 2. Production database evidence

`evidence_amd_generated_theme.json` is a raw export of a production Postgres
row created after a successful request to the AMD-hosted student:

```sql
SELECT row_to_json(t) FROM (
  SELECT id, theme_name, llm_provider, llm_model, created_at, mappings, rationale
  FROM theme_dictionaries WHERE llm_model = 'codeverse-student'
) t;
```

Key fields:

| Field | Value |
|---|---|
| `theme_name` | `Chess` |
| `llm_provider` | `openai_compatible` |
| `llm_model` | `codeverse-student` |
| `created_at` | Production completion timestamp |
| `mappings` | 210 Python concepts expanded by CodeVerse from the AMD-authored semantic profile |

The database transaction happens only after the production backend has sent
the request through the reverse SSH tunnel and received a valid completion.

## 3. Live request correlation

The notebook inference server and production backend emit the same unique
`response_id` and the same 16-character SHA-256 prefix for every completion.
During a demo, keep the notebook cell output and this production log visible
side by side:

```bash
docker compose logs -f backend | grep --line-buffered LLM_INFERENCE_PROOF
```

Clicking an AMD chip produces matching values in both places. This proves that
the browser request crossed the tunnel and returned from `codeverse-student`
on the AMD GPU.

Chip clicks route exclusively to AMD and fail visibly when it is unavailable.
Typed free text always uses the production Fireworks provider.
