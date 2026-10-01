#!/usr/bin/env python
"""Example client that EXECUTES the delegation the harness flags.

The harness decides *whether* an answer should go to a bigger model and says why; it does not make
the cloud call. That is deliberate: the service has no credentials, no vendor SDK and no opinion
about which cloud you use. This file is the missing half, kept in the repo so the pattern is
runnable end to end instead of being a flag nobody acts on.

    local model ──► /decide ──► delegate_to_cloud=true ──► THIS script ──► cloud model
                        │                                                      │
                        └── delegate_reason: high_neutral_mass(0.809>0.7) ◄────┘
                                                                     the answer the user gets

It calls any OpenAI-compatible chat endpoint (OpenAI, Azure OpenAI, Together, vLLM, Ollama…):

    export DELEGATE_API_BASE=https://api.openai.com/v1
    export DELEGATE_API_KEY=sk-...
    export DELEGATE_MODEL=gpt-4o-mini
    python examples/delegate.py "El pedido llegó el martes."

With no API key it runs in **dry-run mode**: it shows the exact request it would send, so the script
is still useful for seeing what the delegation costs without spending anything.

Why a client and not the service: the cost accounting below only makes sense where the budget lives.
The service measures *how often* it delegates (see /metrics); the caller decides whether it can
afford to act on it.

Usage:
    python examples/delegate.py "text to classify" [--url http://127.0.0.1:8090] [--json]
"""
import argparse
import json
import os
import time
import urllib.error
import urllib.request

QUESTION = "Does this text express positive sentiment?"


def ask_harness(url: str, text: str) -> dict:
    payload = {"state": text, "questions": [{"id": "s", "type": "noul", "instructions": QUESTION}]}
    req = urllib.request.Request(url + "/decide", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def ask_cloud(text: str) -> tuple[str, float, dict]:
    """One chat completion, parsed down to 'positive'/'negative'.

    Returns (verdict, latency_ms, raw_response). Raises RuntimeError if the answer cannot be parsed:
    an unparseable cloud answer must not be silently turned into a decision.
    """
    base = os.environ.get("DELEGATE_API_BASE", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("DELEGATE_MODEL", "gpt-4o-mini")
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system",
             "content": "Answer with exactly one word: positive or negative."},
            {"role": "user", "content": f"{QUESTION}\n\nText: {text}"},
        ],
    }
    req = urllib.request.Request(
        base + "/chat/completions", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {os.environ['DELEGATE_API_KEY']}"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = json.load(r)
    latency = (time.perf_counter() - t0) * 1000

    content = (raw.get("choices") or [{}])[0].get("message", {}).get("content", "").strip().lower()
    if content.startswith("positive"):
        return "positive", latency, raw
    if content.startswith("negative"):
        return "negative", latency, raw
    raise RuntimeError(f"could not parse the cloud answer: {content[:80]!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("text", help="the text to classify")
    ap.add_argument("--url", default=os.environ.get("LAYA_SERVICE_URL", "http://127.0.0.1:8090"))
    ap.add_argument("--json", action="store_true", help="print the whole trail as JSON")
    args = ap.parse_args()

    out = ask_harness(args.url, args.text)
    a = out["answers"][0]
    decision = "delegate" if a["delegate_to_cloud"] else "local"
    trail = {"model_local": a.get("model_used"), "decision": decision,
             "confidence": a.get("confidence"), "calibrated": a.get("calibrated"),
             "neutral_mass": a.get("neutral_mass"), "delegate_reason": a.get("delegate_reason"),
             "local_value": a.get("value"), "local_latency_ms": out.get("latency_ms")}

    if decision == "local":
        # The whole point of the harness: most traffic never leaves the machine.
        trail["answer"] = a.get("value")
        trail["answered_by"] = a.get("model_used")
        if args.json:
            print(json.dumps(trail, indent=2))
        else:
            print(f"answered LOCALLY by {a.get('model_used')} "
                  f"(conf {a.get('confidence')}, calibrated={a.get('calibrated')}) in "
                  f"{out.get('latency_ms')} ms")
            print(f"  value = {a.get('value')}")
        return 0

    key = os.environ.get("DELEGATE_API_KEY")
    if not key:
        trail["cloud"] = "dry-run: DELEGATE_API_KEY is not set"
        trail["answer"] = None
        if args.json:
            print(json.dumps(trail, indent=2))
        else:
            print(f"DELEGATED — the local model answered {a.get('value')} at "
                  f"{a.get('confidence')} confidence, which is not good enough:")
            print(f"  reason: {a.get('delegate_reason')}")
            print(f"  neutral mass: {a.get('neutral_mass')}")
            print()
            print("  DRY RUN — no DELEGATE_API_KEY, so nothing was sent. This is the request:")
            print(f"    POST {os.environ.get('DELEGATE_API_BASE', 'https://api.openai.com/v1')}/chat/completions")
            print(f"    model: {os.environ.get('DELEGATE_MODEL', 'gpt-4o-mini')}")
            print(f"    user: {QUESTION} Text: {args.text[:70]}")
            print()
            print("  Set DELEGATE_API_KEY to actually execute it.")
        return 0

    try:
        verdict, latency, raw = ask_cloud(args.text)
    except (urllib.error.URLError, RuntimeError, KeyError) as exc:
        # A failed delegation is not a decision: say so instead of falling back to the local answer,
        # which is exactly the answer the harness had already judged untrustworthy.
        trail["cloud"] = f"failed: {type(exc).__name__}: {exc}"
        trail["answer"] = None
        if args.json:
            print(json.dumps(trail, indent=2))
        else:
            print(f"DELEGATED (reason: {a.get('delegate_reason')}) but the cloud call failed:")
            print(f"  {type(exc).__name__}: {exc}")
            print("  no answer was returned — falling back to the local one would defeat the policy")
        return 2

    usage = raw.get("usage") or {}
    trail.update({"cloud_value": verdict == "positive", "cloud_latency_ms": round(latency, 1),
                  "cloud_model": raw.get("model"), "cloud_tokens": usage.get("total_tokens"),
                  "answer": verdict == "positive", "answered_by": raw.get("model")})
    if args.json:
        print(json.dumps(trail, indent=2))
    else:
        print(f"DELEGATED — local said {a.get('value')} at {a.get('confidence')} conf "
              f"({a.get('delegate_reason')})")
        print(f"cloud  said {'positive' if verdict == 'positive' else 'negative'} in {latency:.0f} ms "
              f"({usage.get('total_tokens', '?')} tokens, model {raw.get('model')})")
        print(f"  -> the user gets: {'positive' if verdict == 'positive' else 'negative'}")
        print(f"  cost of this answer: 1 local call ({out.get('latency_ms')} ms, free) "
              f"+ 1 cloud call ({latency:.0f} ms, paid)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
