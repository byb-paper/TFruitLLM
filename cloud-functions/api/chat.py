import json
import os
import re
import ssl
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler


def encode_json(data):
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def normalize_answer(body):
    """Remove rigid step labels even when the upstream model ignores style rules."""
    try:
        data = json.loads(body.decode("utf-8"))
        for choice in data.get("choices", []):
            message = choice.get("message") or {}
            content = message.get("content")
            if not isinstance(content, str):
                continue
            content = re.sub(
                r"(?i)(?:^|\s+)step\s*(\d+)\s*(?:[—–\-:：]\s*)?",
                lambda match: "\n\n" + match.group(1) + ". ",
                content,
            )
            content = re.sub(
                r"(?:^|\s+)步骤\s*([一二三四五六七八九十\d]+)\s*(?:[—–\-:：]\s*)?",
                lambda match: "\n\n" + match.group(1) + ". ",
                content,
            )
            message["content"] = re.sub(r"\n{3,}", "\n\n", content).strip()
        return encode_json(data)
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        return body


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

            last_user_text = next(
                (
                    str(message.get("content", "")).strip().lower()
                    for message in reversed(messages)
                    if message.get("role") == "user"
                ),
                "",
            )
            greeting_replies = {
                "你好": "你好！请问有什么热带果树研究问题需要帮助？",
                "您好": "您好！请问有什么热带果树研究问题需要帮助？",
                "你好吗": "我很好，谢谢！请问有什么热带果树研究问题需要帮助？",
                "hello": "Hello! How can I help with your tropical fruit research?",
                "hi": "Hello! How can I help with your tropical fruit research?",
                "hey": "Hello! How can I help with your tropical fruit research?",
            }
            if last_user_text in greeting_replies:
                self.send_body(
                    200,
                    encode_json(
                        {
                            "model": "TFruitLLM",
                            "choices": [
                                {
                                    "index": 0,
                                    "message": {
                                        "role": "assistant",
                                        "content": greeting_replies[last_user_text],
                                    },
                                    "finish_reason": "stop",
                                }
                            ],
                        }
                    ),
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
                                "Return only the answer the user needs. Begin directly "
                                "with the substantive answer. Do not restate or quote the "
                                "question, describe the user's intent, explain the response "
                                "rules, or add meta-commentary such as 'the user asks', "
                                "'according to the requirements', or 'here is the answer'. "
                                "Do not add an introduction or conclusion unless it contributes "
                                "new information needed to answer the question. "
                                "Adapt the response structure to the task instead of using "
                                "one fixed template. Give simple factual questions a direct, "
                                "concise paragraph. For multi-part explanations, methods, or "
                                "ordered processes, use only as many numbered items as needed, "
                                "formatted as '1.', '2.', '3.', and so on. For comparisons, "
                                "use compact parallel points or a clear comparison structure. "
                                "For synthesis and research interpretation, use coherent "
                                "scientific paragraphs with a brief conclusion when useful. "
                                "The words 'Step 1', 'Step 2', 'Step', '步骤一', and similar "
                                "process labels are forbidden in the answer. Do not describe "
                                "problem identification, data extraction, completeness checks, "
                                "answer construction, or your reasoning procedure. When the user "
                                "asks which genes, metabolites, pathways, diseases, or studies are "
                                "involved, list the requested items directly, one item per line, "
                                "with a short evidence-based description when available. Avoid "
                                "unnecessary headings, repetitive framing, and rigid four-part "
                                "answers. Keep the length proportional to the question, state "
                                "uncertainty where evidence is insufficient, and use clear "
                                "scientific prose."
                            ),
                        },
                        *messages[-12:],
                    ],
                    "temperature": request_data.get("temperature", 0.3),
                    "max_tokens": min(
                        max(int(request_data.get("max_tokens", 1024)), 64),
                        512,
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
                response_body = normalize_answer(upstream.read())
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
