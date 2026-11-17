import json
import os
import ssl
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler


def encode_json(data):
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


class handler(BaseHTTPRequestHandler):
    def send_body(
        self,
        status,
        body,
        content_type="application/json; charset=utf-8",
    ):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-TFruitLLM-Proxy", "cloud-function-python")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization",
        )
        self.send_header("X-TFruitLLM-Proxy", "cloud-function-python")
        self.end_headers()

    def do_POST(self):
        endpoint = os.getenv("SUGON_CHAT_URL", "").strip()
        if not endpoint:
            self.send_body(
                503,
                encode_json({"error": "SUGON_CHAT_URL is not configured."}),
            )
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            request_data = json.loads(self.rfile.read(length).decode("utf-8"))
            messages = request_data.get("messages", [])

            if not messages:
                question = str(request_data.get("question", "")).strip()
                if question:
                    messages = [{"role": "user", "content": question}]

            if not messages:
                self.send_body(
                    400,
                    encode_json({"error": "A research question is required."}),
                )
                return

            payload = encode_json(
                {
                    "model": "TFruitLLM",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Answer in the same language as the user's question. "
                                "When organizing multiple points, use concise numbered "
                                "items formatted as '1.', '2.', '3.', and '4.'. Never "
                                "write 'Step 1', 'Step 2', or similar step labels. Use "
                                "clear scientific prose and only include as many numbered "
                                "items as the answer requires."
                            ),
                        },
                        *messages[-12:],
                    ],
                    "temperature": request_data.get("temperature", 0.3),
                    "max_tokens": min(
                        max(int(request_data.get("max_tokens", 1024)), 64),
                        2048,
                    ),
                    "stream": False,
                }
            )

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            api_key = os.getenv("SUGON_API_KEY", "").strip()
            if api_key:
                headers["Authorization"] = "Bearer " + api_key

            upstream_request = urllib.request.Request(
                endpoint,
                data=payload,
                headers=headers,
                method="POST",
            )

            # Temporary workaround for the untrusted certificate chain on the
            # current SCNet public endpoint. Remove after SCNet fixes TLS.
            insecure_ssl_context = ssl._create_unverified_context()
            with urllib.request.urlopen(
                upstream_request,
                context=insecure_ssl_context,
                timeout=180,
            ) as upstream:
                response_body = upstream.read()
                content_type = upstream.headers.get(
                    "Content-Type",
                    "application/json; charset=utf-8",
                )
                self.send_body(upstream.status, response_body, content_type)

        except urllib.error.HTTPError as error:
            body = error.read()
            self.send_body(
                error.code,
                body
                or encode_json({"error": "TFruitLLM upstream request failed."}),
            )
        except Exception as error:
            self.send_body(
                502,
                encode_json(
                    {
                        "error": "TFruitLLM proxy request failed.",
                        "detail": str(error),
                    }
                ),
            )
