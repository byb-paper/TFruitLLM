#!/usr/bin/env python3
"""Fetch PubTator BioC chemical annotations for PMIDs in source files."""
from __future__ import annotations
import argparse, csv, json, re, time, urllib.parse, urllib.request
from pathlib import Path

PMID = re.compile(r"(?<!\d)(\d{7,9})(?!\d)")

def collect(path: Path) -> set[str]:
    values=set()
    if path.suffix.lower()==".xlsx":
        from openpyxl import load_workbook
        book=load_workbook(path,read_only=True,data_only=True)
        for sheet in book.worksheets:
            for row in sheet.iter_rows(values_only=True):
                for cell in row:
                    text=str(cell or "")
                    if "pmid" in text.casefold(): continue
                    values.update(PMID.findall(text))
        book.close(); return values
    text=path.read_text(encoding="utf-8",errors="replace")
    if path.suffix.lower()==".jsonl":
        for line in text.splitlines():
            try:
                row=json.loads(line); candidate=str(row.get("pmid", ""))
                if candidate.isdigit(): values.add(candidate)
            except json.JSONDecodeError: pass
    values.update(PMID.findall(text)); return values

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--source",action="append",required=True); ap.add_argument("--output",required=True); ap.add_argument("--batch-size",type=int,default=100); ap.add_argument("--delay",type=float,default=.35); args=ap.parse_args()
    pmids=sorted(set().union(*(collect(Path(x)) for x in args.source)))
    output=Path(args.output); output.parent.mkdir(parents=True,exist_ok=True)
    written=0
    with output.open("w",encoding="utf-8") as handle:
        for start in range(0,len(pmids),args.batch_size):
            batch=pmids[start:start+args.batch_size]
            url="https://www.ncbi.nlm.nih.gov/research/pubtator3-api/publications/export/biocjson?"+urllib.parse.urlencode({"pmids":",".join(batch)})
            try:
                with urllib.request.urlopen(url,timeout=120) as response: raw=response.read().decode("utf-8")
                try:
                    data=json.loads(raw); docs=data if isinstance(data,list) else data.get("documents",[data])
                except json.JSONDecodeError:
                    docs=[json.loads(line) for line in raw.splitlines() if line.strip()]
                for doc in docs: handle.write(json.dumps(doc,ensure_ascii=False)+"\n"); written+=1
                print(f"Fetched {min(start+len(batch),len(pmids))}/{len(pmids)} PMIDs",flush=True)
            except Exception as exc: print(f"WARNING batch {start}: {exc}",flush=True)
            time.sleep(args.delay)
    print(json.dumps({"pmids":len(pmids),"documents":written,"output":str(output)},ensure_ascii=False))
if __name__=="__main__": main()
