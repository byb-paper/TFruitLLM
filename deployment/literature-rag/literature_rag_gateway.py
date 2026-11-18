#!/usr/bin/env python3
"""OpenAI-compatible full-topic literature RAG gateway for TropicalfruitLLM."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def terms(question: str) -> list[str]:
    values = re.findall(r"[A-Za-z][A-Za-z0-9_.-]{2,}", question)
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", question):
        values.extend(run[i : i + length] for length in (5, 4, 3, 2) for i in range(len(run) - length + 1))
    expansions = {
        "芒果": ["mango"], "菠萝": ["pineapple"], "凤梨": ["pineapple"],
        "百香果": ["passion_fruit", "passion fruit"], "牛油果": ["avocado"],
        "番荔枝": ["sugar_apple", "sugar apple"], "番石榴": ["guava"],
        "红毛丹": ["rambutan"], "黄皮": ["wampee"], "火龙果": ["dragon_fruit", "dragon fruit"],
        "荔枝": ["litchi"], "榴莲": ["durian"], "龙眼": ["longan"], "腰果": ["cashew"],
        "采后": ["postharvest", "postharvest_storage_quality"],
        "病害": ["disease", "biotic_stress_disease_pests"], "病原": ["pathogen"],
        "基因": ["gene", "genetics_genomics_breeding"], "转录组": ["transcriptomics_expression"],
        "代谢": ["metabolites_phytochemistry"], "药理": ["nutrition_pharmacology_toxicology"],
        "育种": ["genetics_genomics_breeding"], "胁迫": ["stress"],
        "发育": ["development_flowering_ripening"], "成熟": ["ripening"],
        "栽培": ["cultivation_soil_irrigation"], "微生物组": ["microbiome_endophytes"],
    }
    for marker, extra in expansions.items():
        if marker in question: values.extend(extra)
    return list(dict.fromkeys(values))[:64]


def phrase(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def retrieve(db_path: str, question: str, top_k: int) -> list[dict]:
    words = terms(question)
    if not words: return []
    query = " OR ".join(phrase(x) for x in words)
    sql = """SELECT p.passage_id,p.species,p.topics,p.title,p.text,p.source,
                    p.pmid,p.doi,p.source_type,bm25(passages_fts) AS rank
             FROM passages_fts JOIN passages p USING(passage_id)
             WHERE passages_fts MATCH ? ORDER BY rank LIMIT ?"""
    with sqlite3.connect(db_path) as db:
        rows = db.execute(sql, (query, max(top_k * 5, 40))).fetchall()
    keys = ("passage_id", "species", "topics", "title", "text", "source", "pmid", "doi", "source_type", "rank")
    q = question.casefold()
    species_markers = {
        "芒果": "mango", "mango": "mango", "菠萝": "pineapple", "凤梨": "pineapple",
        "百香果": "passion_fruit", "牛油果": "avocado", "番荔枝": "sugar_apple",
        "番石榴": "guava", "红毛丹": "rambutan", "黄皮": "wampee",
        "火龙果": "dragon_fruit", "荔枝": "litchi", "榴莲": "durian",
        "龙眼": "longan", "腰果": "cashew",
    }
    requested_species = next((value for marker, value in species_markers.items() if marker in q), "")
    output = []
    for row in rows:
        item = dict(zip(keys, row))
        score = -float(item.pop("rank"))
        if item["species"].replace("_", " ") in q: score += 3
        for topic in item["topics"].split("|"):
            if topic.replace("_", " ") in q: score += 2
        if item["pmid"] or item["doi"]: score += 0.5
        item["score"] = score
        output.append(item)
    if requested_species:
        scoped = [item for item in output if item["species"] == requested_species]
        if scoped: output = scoped
    return sorted(output, key=lambda x: x["score"], reverse=True)[:top_k]


def evidence_context(items: list[dict], max_chars: int = 14000) -> str:
    blocks, size = [], 0
    for index, item in enumerate(items, 1):
        refs = []
        if item["pmid"]: refs.append(f"PMID {item['pmid']}")
        if item["doi"]: refs.append(f"DOI {item['doi']}")
        refs.append(item["source"])
        block = (f"[E{index}] Species: {item['species']}; Topics: {item['topics']}\n"
                 f"Title: {item['title']}\nEvidence text: {item['text']}\n"
                 f"Source: {'; '.join(refs)}")
        if size + len(block) > max_chars: break
        blocks.append(block)
        size += len(block)
    return "\n\n".join(blocks)


class Handler(BaseHTTPRequestHandler):
    server_version = "TropicalfruitLLM-Literature-RAG/1.0"

    def send_body(self, code, body, content_type="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)): body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str): body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            try:
                urllib.request.urlopen(self.server.upstream + "/health", timeout=2)
                self.send_body(200, {"status": "ok", "rag": "full_literature_ready"})
            except Exception:
                self.send_body(503, {"status": "loading", "rag": "full_literature_ready", "model": "not_ready"})
        elif self.path == "/v1/models": self.proxy(None)
        else: self.send_body(404, {"error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") != "/v1/chat/completions":
            return self.send_body(404, {"error": "not found"})
        try:
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            messages = payload.get("messages", [])
            question = next((str(x.get("content", "")) for x in reversed(messages) if x.get("role") == "user"), "")
            evidence = retrieve(self.server.db_path, question, self.server.top_k)
            instruction = (
                "直接回答用户真正询问的内容，不要复述问题，不要输出思维过程，也不要机械使用 Step 1/2/3。"
                "可按问题需要选择短句、自然段、项目符号或编号。具体基因、代谢物、表达变化、通路、病原、"
                "PMID、DOI和实验结论必须有下方证据支持，并在相应陈述后标注[E1]。"
                "题名只能证明存在相关文献，不能据此虚构实验结果。证据不足时明确说明缺少什么。"
                "回答末尾列出简短的“证据来源”，保留PMID/DOI。\n\nRETRIEVED EVIDENCE:\n"
                + evidence_context(evidence)
            )
            payload["messages"] = [{"role": "system", "content": instruction}, *messages]
            payload["model"] = self.server.model_name
            payload["stream"] = False
            self.proxy(json.dumps(payload, ensure_ascii=False).encode())
        except Exception as exc:
            self.send_body(500, {"error": str(exc)})

    def proxy(self, data):
        request = urllib.request.Request(
            self.server.upstream + self.path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST" if data is not None else "GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.server.timeout) as response:
                self.send_body(response.status, response.read(), response.headers.get("Content-Type", "application/json"))
        except urllib.error.HTTPError as exc:
            self.send_body(exc.code, exc.read(), exc.headers.get("Content-Type", "application/json"))
        except Exception as exc:
            self.send_body(502, {"error": f"Internal model unavailable: {exc}"})

    def log_message(self, fmt, *args):
        print("[Literature-RAG]", fmt % args, flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=6666)
    parser.add_argument("--upstream", default="http://127.0.0.1:6667")
    parser.add_argument("--model-name", default="TFruitLLM")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.db_path = args.db
    server.upstream = args.upstream.rstrip("/")
    server.model_name = args.model_name
    server.top_k = args.top_k
    server.timeout = args.timeout
    print(f"Full literature RAG on {args.host}:{args.port}; upstream={server.upstream}; db={server.db_path}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
