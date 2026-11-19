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
    chinese_numbers = {
        "一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
        "六": "6", "七": "7", "八": "8", "九": "9", "十": "10",
    }
    try:
        data = json.loads(body.decode("utf-8"))
        for choice in data.get("choices", []):
            message = choice.get("message") or {}
            content = message.get("content")
            if not isinstance(content, str):
                continue
            content = re.sub(
                r"(?i)\bstep\s*(\d+)\s*(?:[—–\-:：]\s*)?",
                lambda match: "\n\n" + match.group(1) + ". ",
                content,
            )
            content = re.sub(
                r"步骤\s*([一二三四五六七八九十\d]+)\s*(?:[—–\-:：]\s*)?",
                lambda match: "\n\n" + chinese_numbers.get(
                    match.group(1), match.group(1)
                ) + ". ",
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

            # The proxy owns the single system prompt. Ignore any system
            # messages supplied by browsers or older cached frontends so the
            # upstream chat template always receives the system message first.
            conversation_messages = [
                message
                for message in messages
                if isinstance(message, dict)
                and message.get("role") in {"user", "assistant"}
            ]
            if not any(
                message.get("role") == "user"
                and str(message.get("content", "")).strip()
                for message in conversation_messages
            ):
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

            identity_questions = {
                "你是谁",
                "你是谁？",
                "你是什么模型",
                "你是什么模型？",
                "who are you",
                "who are you?",
                "what model are you",
                "what model are you?",
            }
            if last_user_text in identity_questions:
                identity_answer = (
                    "我是 TropicalfruitLLM 1.0，一个面向热带果树生物学"
                    "与育种研究的领域大语言模型。本项目当前覆盖的"
                    "13个物种是：菠萝、百香果、鳄梨、番荔枝、番石榴、红毛丹、"
                    "黄皮、火龙果、荔枝、榴莲、龙眼、芒果和腰果。"
                    "不包括柑橘、香蕉和木瓜。"
                )
                self.send_body(
                    200,
                    encode_json(
                        {
                            "model": "TropicalfruitLLM-verified-identity",
                            "choices": [
                                {
                                    "index": 0,
                                    "message": {
                                        "role": "assistant",
                                        "content": identity_answer,
                                    },
                                    "finish_reason": "stop",
                                }
                            ],
                        }
                    ),
                )
                return

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

            # Deterministic correction for a repeatedly hallucinated
            # species–metabolite association. Keep this outside the model so
            # a confident completion cannot override the verified evidence.
            longan_terms = ("龙眼", "longan", "dimocarpus longan")
            mangiferin_terms = ("芒果苷", "mangiferin")
            if any(term in last_user_text for term in longan_terms) and any(
                term in last_user_text for term in mangiferin_terms
            ):
                answer = (
                    "目前没有可靠证据证明龙眼（Dimocarpus longan）果肉、"
                    "果皮或种子中含有芒果苷（mangiferin）。已发表的龙眼"
                    "成分研究主要报道没食子酸、鞣花酸、柯里拉京、表儿茶素、"
                    "槲皮素和原花青素等，现有综述的化合物清单中未列出"
                    "芒果苷。因此严谨的结论是‘尚未发现确证报道’，"
                    "而不是断言绝对不存在。如需实验确认，应使用芒果苷"
                    "标准品进行靶向 LC–MS/MS 或 HPLC 鉴定。可核验来源："
                    "Food Science and Human Wellness 9 (2020) 95–102，"
                    "DOI 10.1016/j.fshw.2020.03.001；PMCID PMC6568221。"
                )
                self.send_body(
                    200,
                    encode_json(
                        {
                            "model": "TFruitLLM-verified-guard",
                            "choices": [
                                {
                                    "index": 0,
                                    "message": {
                                        "role": "assistant",
                                        "content": answer,
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
                                "Write like a friendly, rigorous tropical-fruit research "
                                "colleague. Keep the response natural and approachable rather "
                                "than sounding like a database export, examination rubric, or "
                                "fixed template. Use smooth transitions and briefly connect "
                                "listed findings to their biological meaning when evidence allows. "
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
                                "scientific prose. "
                                "You are TropicalfruitLLM 1.0, not a generic Qwen assistant. "
                                "The project's exact 13-species scope is pineapple, passion "
                                "fruit, avocado, sugar apple, guava, rambutan, wampee, dragon "
                                "fruit, litchi, durian, longan, mango, and cashew. Citrus, "
                                "banana, and papaya are not included in this 13-species scope. "
                                "Never add or substitute species when describing project scope. "
                                "Citation safety is mandatory. This request contains no "
                                "retrieved or independently verified literature records. "
                                "Therefore, never invent or provide specific paper titles, "
                                "authors, journals, publication years, volumes, pages, URLs, "
                                "DOIs, PMIDs, accession numbers, or numbered reference lists "
                                "from memory. Do not imply that a citation was verified merely "
                                "because it sounds plausible. If the user asks for literature "
                                "or sources, say briefly that verified literature retrieval is "
                                "not available in the current public interface, then provide "
                                "useful search keywords or explain what evidence would be "
                                "needed. General biological knowledge may be summarized "
                                "cautiously without citations, but uncertain gene, metabolite, "
                                "pathway, quantitative, or species-specific claims must be "
                                "clearly labeled as unverified rather than guessed."
                            ),
                        },
                        *conversation_messages[-12:],
                    ],
                    "temperature": request_data.get("temperature", 0.4),
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
