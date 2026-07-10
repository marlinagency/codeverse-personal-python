# -*- coding: utf-8 -*-
"""Teacher -> student distillation dataset for the AMD fine-tune demo.

Runs LOCALLY (no GPU needed): calls the Fireworks "teacher" model on hundreds
of diverse theme prompts through the app's REAL prompt builders, validates
every response with the app's REAL parsers, and writes a chat-format JSONL
ready for SFT on the AMD AI Notebook.

Two task types are mixed so the student model learns both app calls:
  - theme profiles        (~70%)  build_theme_profile_messages
  - clarifying questions  (~30%)  build_clarifying_questions_messages

Usage (from repo root):
    .venv/Scripts/python amd/generate_training_data.py --count 600 --workers 8
    .venv/Scripts/python amd/generate_training_data.py --count 8   # pilot

Cost: each sample is one chat call (~1-2k tokens) — hundreds of samples cost
well under $5 of Fireworks credit.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend" / "src"))

from codeverse_api.config import get_settings  # noqa: E402
from codeverse_core.theme_mapping.providers.fireworks import FireworksProvider  # noqa: E402
from codeverse_core.theme_mapping.clarifying_questions import (  # noqa: E402
    build_clarifying_questions_messages,
    parse_clarifying_questions_output,
)
from codeverse_core.theme_mapping.taxonomy_prompts import (  # noqa: E402
    build_theme_profile_messages,
    parse_theme_profile_output,
)

# --------------------------------------------------------------- prompt pool

_INTERESTS_EN = [
    "Counter-Strike 2", "Minecraft", "The Witcher 3", "Valorant", "GTA",
    "chess", "basketball", "Formula 1", "tennis", "surfing", "climbing",
    "beekeeping", "gardening", "baking sourdough bread", "coffee roasting",
    "barbering", "car mechanics", "carpentry", "photography", "astronomy",
    "scuba diving", "sailing", "fishing", "birdwatching", "camping",
    "playing guitar", "piano", "drumming", "DJing", "painting", "pottery",
    "anime", "One Piece", "Naruto", "Harry Potter", "Lord of the Rings",
    "Star Wars", "zombie movies", "true crime podcasts", "K-dramas",
    "nursing", "firefighting", "being a chef", "waiting tables",
    "truck driving", "farming", "teaching kindergarten", "accounting",
    "stock trading", "real estate", "architecture", "interior design",
    "skateboarding", "snowboarding", "boxing", "yoga", "marathon running",
    "dog training", "horseback riding", "aquarium keeping", "model trains",
    "drone racing", "3D printing", "leathercraft", "knitting", "cosplay",
    "urban exploration", "geocaching", "magic tricks", "stand-up comedy",
]

_TEMPLATES_EN = [
    "{x}",
    "I love {x}",
    "I'm really into {x} but {pain} confuse me",
    "I spend all my free time on {x} and I want to learn Python",
    "I work with {x} every day, {pain} feel hard to me",
    "my whole world is {x}, teach me Python through it",
    "{x} is my passion. coding feels alien, especially {pain}",
    "as someone obsessed with {x}, I keep getting stuck on {pain}",
    "total beginner here — I know {x} inside out but Python {pain} make no sense yet",
]

_PAINS_EN = ["loops", "functions", "if/else", "classes", "loops and functions", "dictionaries"]


def build_prompt_pool(seed: int) -> list[str]:
    # English-only by product decision: the app's UI and prompts are English.
    rng = random.Random(seed)
    pool: set[str] = set()
    for interest in _INTERESTS_EN:
        for template in _TEMPLATES_EN:
            pool.add(template.format(x=interest, pain=rng.choice(_PAINS_EN)))
    prompts = sorted(pool)
    rng.shuffle(prompts)
    return prompts


# --------------------------------------------------------------- generation

_print_lock = threading.Lock()


def _one_sample(provider: FireworksProvider, prompt: str, kind: str) -> dict | None:
    """One teacher call, validated with the app's real parser. Returns a chat
    sample or None when the teacher output fails validation (quality filter)."""
    try:
        if kind == "profile":
            messages = build_theme_profile_messages(prompt)
            raw = provider.chat(messages, temperature=0.7, max_tokens=2048)
            parse_theme_profile_output(raw, prompt)  # raises if invalid
        else:
            messages = build_clarifying_questions_messages(prompt)
            # 3072 (not the app's 2048): one-shot generation with no retry
            # loop here, so a roomier budget raises dataset yield.
            raw = provider.chat(messages, temperature=0.7, max_tokens=3072)
            parse_clarifying_questions_output(raw)  # raises if invalid
    except Exception as exc:  # noqa: BLE001 - skip bad samples, log why
        with _print_lock:
            print(f"  [skip:{kind}] {prompt[:40]!r}: {type(exc).__name__}: {str(exc)[:60]}")
        return None

    return {
        "task": kind,
        "prompt": prompt,
        "messages": [*messages, {"role": "assistant", "content": raw}],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=600, help="target sample count")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--out", type=Path, default=Path(__file__).resolve().parent / "codeverse_theme_sft.jsonl"
    )
    parser.add_argument(
        "--questions-ratio", type=float, default=0.3,
        help="fraction of samples that are clarifying-questions tasks",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.fireworks_api_key:
        raise SystemExit("CODEVERSE_FIREWORKS_API_KEY missing (.env)")
    provider = FireworksProvider(
        api_key=settings.fireworks_api_key, model=settings.fireworks_model
    )
    print(f"teacher model: {settings.fireworks_model}")

    prompts = build_prompt_pool(args.seed)
    if args.count > len(prompts):
        print(f"note: only {len(prompts)} unique prompts available, capping count")
    prompts = prompts[: args.count]

    rng = random.Random(args.seed)
    jobs = [
        (prompt, "questions" if rng.random() < args.questions_ratio else "profile")
        for prompt in prompts
    ]

    started = time.time()
    samples: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(_one_sample, provider, prompt, kind) for prompt, kind in jobs]
        for index, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            if result is not None:
                samples.append(result)
            if index % 25 == 0 or index == len(futures):
                elapsed = time.time() - started
                with _print_lock:
                    print(f"  {index}/{len(futures)} done, {len(samples)} valid, {elapsed:.0f}s")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample, ensure_ascii=False) + "\n")

    by_kind = {}
    for sample in samples:
        by_kind[sample["task"]] = by_kind.get(sample["task"], 0) + 1
    print(
        f"\nwrote {len(samples)} validated samples to {args.out}"
        f" (profile={by_kind.get('profile', 0)}, questions={by_kind.get('questions', 0)})"
    )
    print(f"validity rate: {len(samples)}/{len(jobs)}")


if __name__ == "__main__":
    main()
