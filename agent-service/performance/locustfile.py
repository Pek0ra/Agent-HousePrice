"""One reviewed end-to-end workload per Locust process."""
from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path

from locust import HttpUser, between, events, task
from requests.exceptions import Timeout

from stats import classify

CASE = json.loads(Path(os.environ["PERF_CONFIG"]).read_text(encoding="utf-8"))["workloads"][os.environ["PERF_WORKLOAD"]]
KIND = os.environ["PERF_WORKLOAD"]
WARMUP = float(os.environ["PERF_WARMUP"])
SAMPLE = float(os.environ["PERF_SAMPLE"])
MAX_REQUESTS = int(os.environ["PERF_MAX_REQUESTS"])
TIMEOUT = float(os.environ["PERF_TIMEOUT"])
START: float | None = None
random.seed(int(os.environ.get("PERF_SEED", "17")))
RECORDS: list[dict] = []
ACTIVE = 0
ISSUED = 0


@events.spawning_complete.add_listener
def start_measurement(user_count, **kwargs):
    """Start warmup after the configured users have actually been spawned."""
    global START
    START = time.monotonic()


class AgentUser(HttpUser):
    wait_time = between(0.8, 1.2) if KIND == "health" else between(0.1, 0.3)

    @task
    def request(self):
        global ACTIVE, ISSUED
        if START is not None and time.monotonic() - START >= WARMUP + SAMPLE:
            self.environment.runner.quit()
            return
        if ISSUED >= MAX_REQUESTS:
            self.environment.runner.quit()
            return
        ISSUED += 1
        ACTIVE += 1
        inflight = ACTIVE
        phase = "warmup" if START is None or time.monotonic() - START < WARMUP else "sample"
        started = time.perf_counter()
        at = time.time()
        status = None
        trace_header = None
        server_duration = None
        body = None
        error = None
        category = None
        try:
            path = "/health" if KIND == "health" else "/api/v1/chat"
            payload = None if KIND == "health" else {"message": CASE["question"]}
            with self.client.request("GET" if KIND == "health" else "POST", path, json=payload,
                                     timeout=TIMEOUT, catch_response=True, name=KIND) as response:
                status = response.status_code
                trace_header = response.headers.get('X-Trace-ID')
                try:
                    server_duration = float(response.headers['X-Server-Duration-Ms'])
                except (KeyError, ValueError):
                    pass
                try:
                    body = response.json()
                except ValueError:
                    body = None
                category = ("success" if status == 200 and body == {"status": "ok"} else "business_failure") if KIND == "health" else classify(status, body, None, CASE)
                if category != "success":
                    response.failure(category)
        except Timeout:
            error = "timeout"
        except Exception:
            error = "network_failure"
        finally:
            duration = round((time.perf_counter() - started) * 1000, 3)
            body = body if isinstance(body, dict) else None
            details = (body or {}).get("details") or {}
            category = ("timeout" if error == "timeout" else "network_failure") if error else category
            spans = {key: details.get(key) for key in ("jev_duration_ms", "route_duration_ms", "llm_duration_ms",
                "qdrant_duration_ms", "rerank_duration_ms", "mysql_duration_ms", "hive_duration_ms", "duration_ms")}
            spans['duration_ms'] = server_duration if server_duration is not None else details.get('duration_ms')
            calls = details.get("policy_tool_calls") or []
            spans["policy_tool_duration_ms"] = sum(call["duration_ms"] for call in calls if isinstance(call.get("duration_ms"), (int, float))) if calls else None
            checks = CASE.get('assertions', {})
            answer = str((body or {}).get('answer') or '')
            diagnostics = ({'missing_terms': [term for term in checks.get('answer_all', []) if term not in answer],
                            'answer_any_matched': any(term in answer for term in checks.get('answer_any', [])) if checks.get('answer_any') else None,
                            'evidence_count': len(details.get('policy_evidence') or []),
                            'row_count': len((body or {}).get('rows') or [])} if category == 'business_failure' else None)
            if category is not None:
                RECORDS.append({"at": at, "phase": phase, "category": category, "status": status,
                "duration_ms": duration, "inflight": inflight, "trace_id": (body or {}).get("trace_id") or trace_header,
                "source": details.get("data_source"), "route_reason": details.get("route_reason"),
                "error_category": details.get("error_category"),
                "successful_queries": details.get("successful_queries"), "model_calls": details.get("model_calls"),
                "llm_calls": details.get("llm_calls") or [],
                "prompt_tokens": details.get("prompt_tokens"), "completion_tokens": details.get("completion_tokens"),
                "spans": spans, "assertion_diagnostics": diagnostics})
            ACTIVE -= 1


@events.test_stop.add_listener
def save_records(environment, **kwargs):
    path = Path(os.environ["PERF_RECORDS"])
    elapsed = max(0.0, min(SAMPLE, time.monotonic() - START - WARMUP)) if START is not None else 0.0
    Path(str(path) + '.meta.json').write_text(json.dumps({'sample_elapsed_s': round(elapsed, 3),
        'all_users_spawned': START is not None, 'issued_requests': ISSUED}), encoding='utf-8')
    with path.open("x", encoding="utf-8") as stream:
        for row in RECORDS:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
