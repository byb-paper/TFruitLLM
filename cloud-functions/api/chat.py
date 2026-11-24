import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler


def encode_json(data):
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


GENOME_RESOURCES = (
    ("菠萝", "Ananas comosus", ("菠萝", "pineapple", "ananas comosus")),
    ("百香果", "Passiflora edulis", ("百香果", "passion fruit", "passionfruit", "passiflora edulis")),
    ("鳄梨", "Persea americana", ("鳄梨", "牛油果", "avocado", "persea americana")),
    ("番荔枝", "Annona squamosa", ("番荔枝", "sugar apple", "sweetsop", "annona squamosa")),
    ("番石榴", "Psidium guajava", ("番石榴", "guava", "psidium guajava")),
    ("红毛丹", "Nephelium lappaceum", ("红毛丹", "rambutan", "nephelium lappaceum")),
    ("黄皮", "Clausena lansium", ("黄皮", "wampee", "wampi", "clausena lansium")),
    ("火龙果", "Selenicereus undatus", ("火龙果", "dragon fruit", "pitaya", "selenicereus undatus", "hylocereus undatus")),
    ("荔枝", "Litchi chinensis", ("荔枝", "litchi", "lychee", "litchi chinensis")),
    ("榴莲", "Durio zibethinus", ("榴莲", "durian", "durio zibethinus")),
    ("龙眼", "Dimocarpus longan", ("龙眼", "longan", "dimocarpus longan")),
    ("芒果", "Mangifera indica", ("芒果", "mango", "mangifera indica")),
    ("腰果", "Anacardium occidentale", ("腰果", "cashew", "anacardium occidentale")),
)


def genome_resource_text(resources):
    blocks = []
    for chinese_name, scientific_name, _aliases in resources:
        encoded_name = urllib.parse.quote(scientific_name)
        datasets_url = (
            "https://www.ncbi.nlm.nih.gov/datasets/genome/?taxon="
            + encoded_name
        )
        assembly_query = urllib.parse.quote(f'"{scientific_name}"[Organism]')
        assembly_url = (
            "https://www.ncbi.nlm.nih.gov/assembly/?term=" + assembly_query
        )
        filename = scientific_name.lower().replace(" ", "_") + "_genome.zip"
        blocks.append(
            f"{chinese_name}（{scientific_name}）\n"
            f"NCBI Datasets 基因组与在线下载：{datasets_url}\n"
            f"NCBI Assembly 记录：{assembly_url}\n"
            "NCBI Datasets 命令行下载："
            f'datasets download genome taxon "{scientific_name}" '
            f'--include genome,gff3,rna,cds,protein --filename {filename}'
        )
    notice = (
        "\n\n注意：同一物种可能有多个品种和组装版本。下载前请在 "
        "NCBI Datasets 页面核对 Assembly accession、品种、组装层级、"
        "注释情况和发布日期，不要默认第一条记录就是最适合的参考基因组。"
    )
    return "\n\n".join(blocks) + notice


def match_genome_resources(text):
    """Match the longest non-overlapping species names in a query."""
    candidates = []
    for resource_index, resource in enumerate(GENOME_RESOURCES):
        for alias in resource[2]:
            start = text.find(alias)
            while start >= 0:
                candidates.append(
                    (len(alias), start, start + len(alias), resource_index)
                )
                start = text.find(alias, start + 1)
    occupied = []
    selected = []
    for _length, start, end, resource_index in sorted(
        candidates, reverse=True
    ):
        if any(start < used_end and end > used_start for used_start, used_end in occupied):
            continue
        occupied.append((start, end))
        if resource_index not in selected:
            selected.append(resource_index)
    return [GENOME_RESOURCES[index] for index in sorted(selected)]


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
                    "我是 TropicalfruitLLM v1.0，一个面向热带果树生物学"
                    "与育种研究的领域大语言模型。本项目当前覆盖的"
                    "13个物种是：菠萝、百香果、鳄梨、番荔枝、番石榴、红毛丹、"
                    "黄皮、火龙果、荔枝、榴莲、龙眼、芒果和腰果。"
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

            genome_terms = ("基因组", "genome", "assembly", "组装")
            if any(term in last_user_text for term in genome_terms):
                matched_resources = match_genome_resources(last_user_text)
                if not matched_resources and any(
                    term in last_user_text
                    for term in ("13个物种", "13种", "全部", "all species")
                ):
                    matched_resources = list(GENOME_RESOURCES)
                if matched_resources:
                    self.send_body(
                        200,
                        encode_json(
                            {
                                "model": "TropicalfruitLLM-genome-resources",
                                "choices": [
                                    {
                                        "index": 0,
                                        "message": {
                                            "role": "assistant",
                                            "content": genome_resource_text(
                                                matched_resources
                                            ),
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
                                "你是 TropicalfruitLLM v1.0，一位严谨、自然的热带果树研究助手。"
                                "使用与用户相同的语言，直接给出准确、可读的生物学答案。"
                                "简单问题用简洁段落；需要列举时用 1.、2.、3.，每项写名称和作用。"
                                "项目范围严格为菠萝、百香果、鳄梨、番荔枝、番石榴、红毛丹、"
                                "黄皮、火龙果、荔枝、榴莲、龙眼、芒果和腰果。"
                                "只陈述有把握的内容；没有可靠来源时不生成具体文献或数据库编号。"
                            ),
                        },
                        next(
                            message
                            for message in reversed(conversation_messages)
                            if message.get("role") == "user"
                        ),
                    ],
                    "temperature": min(
                        float(request_data.get("temperature", 0.2)), 0.2
                    ),
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
