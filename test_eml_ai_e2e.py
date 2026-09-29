# test_eml_ai_e2e.py — manual E2E: run all sample .eml files through the real
# parser + LLM extraction chain (free OpenRouter models only).
#
# Usage:  OPENROUTER_API_KEY=sk-or-... python test_eml_ai_e2e.py
# (skipped by pytest when the key is not set)
import asyncio
import glob
import os
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("OPENROUTER_API_KEY"), reason="OPENROUTER_API_KEY not set"
)

from services.eml_processor import (  # noqa: E402
    build_llm_prompt,
    extract_local_fields,
    merge_fields,
    parse_eml_bytes,
)
from services.llm_router import ChainEntry, extract_json  # noqa: E402

SAMPLE_DIR = "eml examples/EML Files for Testing"


def build_free_chain(key: str) -> list[ChainEntry]:
    models = [
        "qwen/qwen3.8-27b:free",
        "google/gemma-4-31b-it:free",
        "thinkingmachines/inkling:free",
        "openrouter/free",
    ]
    return [ChainEntry(provider="openrouter", model=m, api_key=key) for m in models]


async def run(key: str) -> int:
    files = sorted(glob.glob(os.path.join(SAMPLE_DIR, "*.eml")))
    if not files:
        print(f"No .eml files in {SAMPLE_DIR}")
        return 1
    chain = build_free_chain(key)
    budget = float(os.getenv("EML_PROCESS_BUDGET", "1800"))
    deadline = time.monotonic() + budget
    llm = fallback = errors = 0
    extracted = 0
    t0 = time.time()
    for i, path in enumerate(files, 1):
        name = os.path.basename(path)
        t1 = time.time()
        try:
            raw = open(path, "rb").read()
            parsed = parse_eml_bytes(raw, name)
            local = extract_local_fields(parsed)
            ai = await extract_json(chain, build_llm_prompt(parsed), deadline)
            merged = merge_fields(local, ai)
            if ai:
                llm += 1
            else:
                fallback += 1
            got = [f for f in ("name", "email", "phone_primary", "company") if merged.get(f)]
            extracted += bool(got)
            dt = time.time() - t1
            print(
                f"[{i:2}/{len(files)}] {'llm     ' if ai else 'fallback'} {dt:5.1f}s "
                f"fields={len(got)} name={merged.get('name') or '-'} "
                f"email={merged.get('email') or '-'} phone={merged.get('phone_primary') or '-'}",
                flush=True,
            )
        except Exception as exc:
            errors += 1
            print(f"[{i:2}/{len(files)}] ERROR    {time.time() - t1:5.1f}s {exc}", flush=True)
    total = time.time() - t0
    print(
        f"\nDone: {len(files)} files in {total:.0f}s | llm={llm} fallback={fallback} "
        f"errors={errors} with-fields={extracted} budget={budget:.0f}s"
    )
    if errors:
        return 1
    if llm == 0:
        print("FAIL: no file got LLM extraction (rate-limited or all providers timed out)")
        return 1
    return 0


if __name__ == "__main__":
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("Set OPENROUTER_API_KEY")
        sys.exit(2)
    sys.exit(asyncio.run(run(key)))
