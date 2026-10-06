"""Shared OpenRouter chat call with retries.

The free-tier models this pipeline uses regularly return transient failures -- 429 rate
limits, 5xx, or a 200 with content: null -- and a single unretried failure used to crash a
whole pipeline step. Every script calls the model through chat() so retry behavior can't
drift between them.
"""
import json
import threading
import time

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4
# Free models allow ~20 requests/minute; stay at 15 so per-minute 429s don't happen at all.
MIN_INTERVAL_S = 4.0
_next_slot = 0.0
_slot_lock = threading.Lock()


def _throttle():
    """Thread-safe: hands each request the next free 4s slot, so any number of worker threads
    together stay under the per-minute limit while their waiting on the model overlaps."""
    global _next_slot
    with _slot_lock:
        now = time.monotonic()
        start = max(now, _next_slot)
        _next_slot = start + MIN_INTERVAL_S
    if start > now:
        time.sleep(start - now)


class OpenRouterError(RuntimeError):
    pass


class DailyQuotaExceeded(OpenRouterError):
    """The account's free-models-per-day cap is used up. Retrying can't help until it resets
    (00:00 UTC), and every retry would just be another wasted request -- callers should stop
    making calls for the rest of the run."""


def chat(prompt, api_key, model, timeout=120, json_mode=False):
    """Return the model's text content (parsed dict if json_mode), retrying transient failures."""
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        # This model spends thousands of tokens on chain-of-thought before ever writing an
        # answer, and unbounded reasoning frequently exhausts its budget and returns
        # content: null (finish_reason "error") instead of the answer. Disabling it gets a
        # direct, fast answer.
        "reasoning": {"enabled": False},
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            _throttle()
            resp = requests.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=body,
                timeout=timeout,
            )
            if resp.status_code == 429 and "per-day" in resp.text:
                raise DailyQuotaExceeded(
                    "OpenRouter free-models-per-day limit reached (50/day without credits; "
                    "1000/day after a one-time 10-credit top-up). Resets at 00:00 UTC.")
            if resp.status_code in RETRYABLE_STATUS:
                raise OpenRouterError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            resp.raise_for_status()

            content = resp.json()["choices"][0]["message"]["content"]
            if not content or not content.strip():
                raise OpenRouterError("empty content (model returned null)")
            content = content.strip()
            return _parse_json(content) if json_mode else content
        except DailyQuotaExceeded:
            raise
        except (OpenRouterError, requests.ConnectionError, requests.Timeout,
                json.JSONDecodeError, KeyError, IndexError) as e:
            last_error = e
            if attempt < MAX_ATTEMPTS:
                # Per-minute 429s need a longer wait than a flaky 5xx does.
                time.sleep((10 if "HTTP 429" in str(e) else 2) * attempt)

    raise OpenRouterError(f"failed after {MAX_ATTEMPTS} attempts: {last_error}")


def _parse_json(content):
    # Some free models wrap JSON in ```json fences despite being told not to.
    if content.startswith("```"):
        content = content.strip("`").removeprefix("json").strip()
    return json.loads(content)
