#!/usr/bin/env python3
"""OpenAI-compatible RAG gateway for TropicalfruitLLM.

Public port 6666 -> retrieve SQLite evidence -> internal vLLM port 6667.
Only retrieved source passages may support concrete metabolite/gene claims.
"""
from __future__ import annotations
import argparse, json, re, sqlite3, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

def terms(question: str) -> list[str]:
    values = re.findall(r"[A-Za-z][A-Za-z0-9_.-]{2,}", question)
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", question):
        values.extend(run[i:i+n] for n in (4,3,2) for i in range(len(run)-n+1))
    return list(dict.fromkeys(values))[:48]

def phrase(value: str) -> str: return '"' + value.replace('"','""') + '"'

def retrieve(db_path: str, question: str, top_k: int = 8) -> list[dict]:
    words = terms(question)
    if not words: return []
    query = " OR ".join(phrase(x) for x in words)
    sql = """SELECT p.passage_id,p.species,p.metabolite,p.title,p.text,p.source,p.pmid,p.doi,bm25(passages_fts) rank
             FROM passages_fts JOIN passages p USING(passage_id)
             WHERE passages_fts MATCH ? ORDER BY rank LIMIT ?"""
    with sqlite3.connect(db_path) as db:
        rows = db.execute(sql,(query,max(top_k*3,20))).fetchall()
    scored=[]
    q=question.casefold()
    for row in rows:
        item=dict(zip(("passage_id","species","metabolite","title","text","source","pmid","doi","rank"),row))
        item["score"]=-float(item.pop("rank")) + (3 if item["metabolite"].casefold() in q else 0) + (2 if item["species"].replace('_',' ') in q else 0)
        scored.append(item)
    return sorted(scored,key=lambda x:x["score"],reverse=True)[:top_k]

def context(items: list[dict], max_chars: int=12000) -> str:
    blocks=[]; size=0
    for i,x in enumerate(items,1):
        cite="; ".join(v for v in [f"PMID {x['pmid']}" if x['pmid'] else "",f"DOI {x['doi']}" if x['doi'] else "",x['source']] if v)
        block=f"[E{i}] Species: {x['species']}; Metabolite: {x['metabolite']}\nTitle: {x['title']}\nEvidence: {x['text']}\nSource: {cite}"
        if size+len(block)>max_chars: break
        blocks.append(block); size+=len(block)
    return "\n\n".join(blocks)

class Handler(BaseHTTPRequestHandler):
    server_version="TropicalfruitLLM-RAG/1.0"
    def send(self,code,body,ctype="application/json; charset=utf-8"):
        if isinstance(body,(dict,list)): body=json.dumps(body,ensure_ascii=False).encode()
        elif isinstance(body,str): body=body.encode()
        self.send_response(code); self.send_header("Content-Type",ctype); self.send_header("Content-Length",str(len(body))); self.send_header("Access-Control-Allow-Origin","*"); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path=="/health":
            try: urllib.request.urlopen(self.server.upstream+"/health",timeout=2); self.send(200,{"status":"ok","rag":"ready"})
            except Exception: self.send(503,{"status":"loading","rag":"ready","model":"not_ready"})
        elif self.path=="/v1/models": self.proxy(None)
        else: self.send(404,{"error":"not found"})
    def do_POST(self):
        if self.path.rstrip("/")!="/v1/chat/completions": return self.send(404,{"error":"not found"})
        try:
            length=int(self.headers.get("Content-Length","0")); payload=json.loads(self.rfile.read(length))
            messages=payload.get("messages",[]); question=next((str(x.get("content","")) for x in reversed(messages) if x.get("role")=="user"),"")
            evidence=retrieve(self.server.db_path,question,self.server.top_k)
            grounding=("Use only the evidence below for specific metabolite, gene, expression, pathway, PMID or DOI claims. "
                       "If evidence is insufficient, say so explicitly; do not invent genes or citations. "
                       "Answer in the user's language. Cite supporting statements as [E1], [E2]. End with a short 'Evidence' list containing PMID/DOI/source.\n\nRETRIEVED EVIDENCE:\n"+context(evidence))
            payload["messages"]=[{"role":"system","content":grounding},*messages]
            payload["model"]=self.server.model_name; payload["stream"]=False
            self.proxy(json.dumps(payload,ensure_ascii=False).encode())
        except Exception as exc: self.send(500,{"error":str(exc)})
    def proxy(self,data):
        url=self.server.upstream+self.path
        req=urllib.request.Request(url,data=data,headers={"Content-Type":"application/json"},method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req,timeout=self.server.timeout) as response: self.send(response.status,response.read(),response.headers.get("Content-Type","application/json"))
        except urllib.error.HTTPError as exc: self.send(exc.code,exc.read(),exc.headers.get("Content-Type","application/json"))
        except Exception as exc: self.send(502,{"error":f"Internal model unavailable: {exc}"})
    def log_message(self,fmt,*args): print("[RAG]",fmt%args,flush=True)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--db",required=True); ap.add_argument("--host",default="0.0.0.0"); ap.add_argument("--port",type=int,default=6666); ap.add_argument("--upstream",default="http://127.0.0.1:6667"); ap.add_argument("--model-name",default="TFruitLLM"); ap.add_argument("--top-k",type=int,default=8); ap.add_argument("--timeout",type=int,default=300); args=ap.parse_args()
    server=ThreadingHTTPServer((args.host,args.port),Handler); server.db_path=args.db; server.upstream=args.upstream.rstrip('/'); server.model_name=args.model_name; server.top_k=args.top_k; server.timeout=args.timeout
    print(f"RAG gateway listening on {args.host}:{args.port}; upstream={server.upstream}; db={args.db}",flush=True); server.serve_forever()
if __name__=="__main__": main()
