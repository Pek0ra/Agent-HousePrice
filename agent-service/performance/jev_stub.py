"""Local test-only TypeSafe-compatible routing stub; control binds to loopback."""
from __future__ import annotations

import argparse
import json
import socket
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODE = "normal"
DELAY = 10.0


def choice(options: list[str], selected: str) -> dict:
    return {"type": "choice", "choice": selected, "probabilities": {key: 1.0 if key == selected else 0.0 for key in options}, "confidence": 1.0}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_POST(self):
        global MODE
        if self.path == "/control" and self.client_address[0] in {"127.0.0.1", "::1"}:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            if body.get("mode") not in {"normal", "timeout", "disconnect"}:
                self.send_error(400)
                return
            MODE = body["mode"]
            self.reply({"mode": MODE})
            return
        if self.path != "/v1/systemone":
            self.send_error(404)
            return
        if MODE == "disconnect":
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        if MODE == "timeout":
            time.sleep(DELAY)
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        question = body.get("state", {}).get("current_question", "")
        requested = body.get("questions", {})
        intent = "aggregation" if any(word in question for word in ("数量", "多少", "平均")) else "policy"
        scope = "current_listing" if intent == "aggregation" else "policy"
        answers = {}
        for name in ("intent", "scope", "explicit_import"):
            options = list(requested[name]["criteria"])
            selected = {"intent": intent, "scope": scope, "explicit_import": "no"}[name]
            answers[name] = choice(options, selected)
        answers["depends_on_previous"] = {"type": "noul", "noul": 0.0}
        answers["multiple_tasks"] = {"type": "noul", "noul": 0.0}
        try:
            self.reply({"answers": answers})
        except (BrokenPipeError, ConnectionResetError):
            pass

    def reply(self, body):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--delay", type=float, default=10)
    args = parser.parse_args()
    global DELAY
    DELAY = args.delay
    ThreadingHTTPServer(("0.0.0.0", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
