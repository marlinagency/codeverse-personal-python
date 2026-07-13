# Live AMD Inference Proof

Use three visible panes. This proves the request path instead of relying on a
UI badge.

## 1. AMD notebook

Run the GPU sanity cell and keep its output visible:

```text
gpu available: True
device: AMD Instinct ...
```

Run the OpenAI-compatible serving cell once. Every chip request now prints:

```text
[AMD LIVE INFERENCE] model=codeverse-student gpu='AMD Instinct ...'
response_id=chatcmpl-cv-... latency_ms=... output_sha256=...
```

Keep the reverse SSH tunnel running in the JupyterLab terminal.

## 2. CodeVerse production terminal

SSH into the production host and follow only inference proof events:

```bash
cd /opt/codeverse
docker compose logs -f backend | grep --line-buffered LLM_INFERENCE_PROOF
```

The backend line must show `requested_model=codeverse-student`, the same
`response_id`, and the same `output_sha256` as the AMD notebook.

Optional tunnel check:

```bash
curl -s http://localhost:8001/v1/models | python -m json.tool
```

## 3. Browser

1. Open the deployed CodeVerse application.
2. Click a chip under `Themes tuned on AMD Instinct`, such as `chess`.
3. Keep the notebook and production terminal visible while it completes.
4. Match the `response_id` and `output_sha256` in both logs.
5. Show the result page's `Live AMD result` badge and `codeverse-student` name.
6. Open the dictionary to show the complete 210-concept Python vocabulary.

Do not type the theme into the free-text field for this proof. Free text uses
Fireworks by product design; only the curated chips use the AMD student model.

## 30-second narration

> The free-text production path uses Fireworks, while these curated chips are
> routed exclusively to our Gemma student fine-tuned on AMD Instinct. I am
> clicking Chess now. The AMD notebook received the request on the Instinct
> GPU and generated the response ID shown here. The production backend received
> the same response ID and output hash through our reverse tunnel. CodeVerse
> then expanded that AMD-authored semantic profile into 210 validated Python
> mappings. If the AMD instance is unavailable, the product remains online by
> falling back to Fireworks, while its provenance clearly identifies which
> engine actually answered.
