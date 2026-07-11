# CodeVerse — Personal Python

**Turn how you think into Python.** CodeVerse builds a personalized Python
syntax layer from any free-text description of who you are ("I'm a beekeeper
and loops confuse me"), then teaches you real Python through it — with real,
running code at every step.

Built for the AMD Developer Hackathon (Track 3).

## How it works

1. **Describe your world** — any hobby, job, game, or fandom, in one sentence.
2. **Answer a 7-question wizard** — the LLM generates clarifying questions
   *about your specific world* (a beekeeper gets hive questions) to ground
   the personalization.
3. **Get your personal Python** — ~210 concepts (keywords, builtins, methods)
   renamed into your world's vocabulary: for a beekeeper, `if` becomes
   `queen_presence`, `for` becomes `foraging_cycle`, `print` becomes
   `harvest_report`. No curated tables — one LLM "brain" handles any theme.
4. **Write and run it for real** — a lexer → parser (UASL) → codegen pipeline
   compiles your personal syntax to real Python, executed in Docker-sandboxed
   containers. Errors come back translated into your theme's vocabulary.
5. **Learn through a real curriculum** — a diagnosis-driven 9-module path
   (conditions → loops → functions → collections → OOP → errors) with:
   - runnable themed lessons and side-by-side real-Python previews
   - quiz practice with hints, teaching feedback, and mastery grading
   - **write-the-code exercises** evaluated behaviorally (compile → run →
     compare output), every one test-proven solvable for any theme
   - persistent per-module progress (resume where you left off)
   - a **graduation capstone**: rewrite a personal-syntax program in real,
     standard Python — with an anti-cheat check that rejects submissions
     still using personal tokens. The scaffold comes off.

## Architecture

```
free text ─▶ Clarifying wizard ─▶ Theme profile (LLM = the brain)
                                        │
                              concept dictionary (~210 tokens)
                                        │
   Personal Python source ─▶ lexer ─▶ UASL ─▶ Python codegen ─▶ Docker sandbox
                                        │                            │
                              themed diagnostics ◀───────── real output
```

- **Backend**: FastAPI + SQLAlchemy (Postgres/SQLite), 300+ tests
- **Frontend**: React + Vite + Monaco
- **LLM**: Fireworks AI (`glm-5p2` default; provider-agnostic — OpenAI-compatible,
  Anthropic, and a deterministic offline fake are one config switch away)
- **Execution**: per-run sibling Docker containers with CPU/memory/time limits

## AMD platform usage

See [`amd/README.md`](amd/README.md): a teacher→student distillation pipeline —
the Fireworks teacher generates a validated training set from the app's real
prompts, and the product spec's intended production model (**Gemma 4**) is
LoRA fine-tuned **on AMD Instinct GPUs with ROCm** (AMD AI Notebooks), served
with **vLLM** as an OpenAI-compatible endpoint, and plugged into the app with
a one-line provider switch. The public
demo itself is hosted on **AMD Developer Cloud** ([`DEPLOY.md`](DEPLOY.md)).

## Run it locally

```bash
# backend (Python 3.12)
python -m venv .venv && .venv/Scripts/pip install -e backend
.venv/Scripts/python -m uvicorn codeverse_api.main:app --reload --app-dir backend/src

# frontend
cd frontend && npm install && npm run dev   # http://localhost:5173

# tests
.venv/Scripts/python -m pytest backend/tests -q
```

Copy `.env.example` → `.env` and set `CODEVERSE_LLM_PROVIDER=fireworks` +
your API key (or leave `fake` for a fully offline deterministic demo).

## Deploy the public demo

See [`DEPLOY.md`](DEPLOY.md) — one Docker Compose stack (nginx frontend +
API + Postgres + sandbox runtimes) with per-visitor isolated accounts.
