"""A fake OpenAI-compatible server for testing the proxy without a real API key.

Run this, point the backend's OPENAI_BASE_URL at it, and any request that goes
through the proxy will get a canned reply instead of a real model response.
No cost, no real key needed — useful for checking auth, caps, logging, and
cost tracking end to end.

    python mock_upstream.py

Then in another terminal, run the backend with:

    OPENAI_BASE_URL=http://127.0.0.1:8099/v1 uvicorn app.main:app --reload --port 8000

And enter any placeholder text (e.g. "sk-fake-test-key") as the OpenAI key in
Settings — the mock server doesn't check it.
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8099


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(length) or "{}")
        model = body.get("model", "unknown-model")

        if body.get("stream"):
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.end_headers()
            for chunk in [
                {"choices": [{"delta": {"content": "Hello"}}]},
                {"choices": [{"delta": {"content": " from the "}}]},
                {"choices": [{"delta": {"content": f"mock {model} server!"}}]},
                {"choices": [], "usage": {"prompt_tokens": 42, "completion_tokens": 18}},
            ]:
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            return

        payload = {
            "id": "chatcmpl-mock123",
            "object": "chat.completion",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": (
                            f"Hello! This is a fake reply from the mock server standing in "
                            f"for {model}. No real API was called, and no money was spent."
                        ),
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 42, "completion_tokens": 18, "total_tokens": 60},
        }
        out = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, format, *args):
        print(f"[mock upstream] {self.command} {self.path} — {format % args}")


if __name__ == "__main__":
    print(f"Mock upstream running on http://127.0.0.1:{PORT}")
    print("Point OPENAI_BASE_URL at http://127.0.0.1:8099/v1 to use it.\n")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
