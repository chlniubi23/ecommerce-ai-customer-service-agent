from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_BASE_URL = "http://localhost:8000"


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 15.0,
) -> tuple[int, dict[str, Any]]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        return response.status, json.loads(raw) if raw else {}


def check_health(base_url: str) -> CheckResult:
    try:
        status, data = request_json("GET", f"{base_url}/health", timeout=8.0)
        ok = status == 200 and data.get("success") is True
        detail = data.get("data", {}).get("status", data)
        return CheckResult("health", ok, str(detail))
    except Exception as exc:
        return CheckResult("health", False, str(exc))


def check_chat(base_url: str, message: str) -> CheckResult:
    payload = {
        "message": message,
        "history": [],
        "session_id": "smoke_test_session",
    }
    try:
        status, data = request_json("POST", f"{base_url}/api/v1/chat", payload, timeout=45.0)
        reply = ((data.get("data") or {}).get("reply") or {}).get("content", "")
        ok = status == 200 and data.get("success") is True and bool(reply)
        detail = reply[:120] if reply else data.get("error", data)
        return CheckResult("chat", ok, str(detail))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return CheckResult("chat", False, f"HTTP {exc.code}: {raw[:300]}")
    except Exception as exc:
        return CheckResult("chat", False, str(exc))


def print_result(result: CheckResult) -> None:
    status = "PASS" if result.ok else "FAIL"
    print(f"[{status}] {result.name}: {result.detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal smoke test for the commerce agent backend.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Backend base URL.")
    parser.add_argument("--message", default="你好", help="Message used for the chat smoke check.")
    parser.add_argument("--skip-chat", action="store_true", help="Only check /health.")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    results = [check_health(base_url)]
    if not args.skip_chat:
        results.append(check_chat(base_url, args.message))

    for result in results:
        print_result(result)

    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
