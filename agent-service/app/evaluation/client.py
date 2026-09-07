from __future__ import annotations

import time
import httpx


class AgentClient:
    def __init__(self, url: str, timeout: float) -> None:
        self.url = url
        self.client = httpx.Client(timeout=timeout)

    def health(self) -> None:
        health_url = self.url.split("/api/v1/chat", 1)[0] + "/health"
        response = self.client.get(health_url)
        response.raise_for_status()
        if response.json().get("status") != "ok": raise RuntimeError("健康检查未返回 status=ok")

    def capabilities(self) -> dict:
        url = self.url.split("/api/v1/chat", 1)[0] + "/api/v1/capabilities"
        response = self.client.get(url); response.raise_for_status(); return response.json()

    def verify_snapshot_count(self, expected: int = 5000) -> None:
        status, _, body, _ = self.ask("当前全部出售和出租房源合计有多少条？", None)
        rows = (body or {}).get("rows") or []
        values = [value for row in rows for value in row if isinstance(value, (int, float))]
        if status != 200 or expected not in values:
            raise RuntimeError(f"活动数据库计数与快照不一致：期望 {expected}，实际 {values or '无结果'}")

    def ask(self, message: str, thread_id: str | None) -> tuple[int, float, dict | None, str]:
        started = time.perf_counter()
        response = self.client.post(self.url, json={"message": message, **({"thread_id": thread_id} if thread_id else {})})
        elapsed = (time.perf_counter() - started) * 1000
        try: body = response.json()
        except ValueError: body = None
        return response.status_code, elapsed, body, response.text

    def close(self) -> None: self.client.close()
