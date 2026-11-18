#!/usr/bin/env python3
"""Build evidence-grounded metabolite QA and SQLite KG-RAG for 13 fruits.

The builder scans existing SFT JSONL, PubMed/literature tables and optional
PubTator chemical annotations. Every generated QA item and KG edge retains its
source. ``--strict`` fails when a catalogued metabolite has no source evidence.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, re, sqlite3
from collections import defaultdict
from pathlib import Path

SPECIES = {
    "mango": ["mango", "Mangifera indica", "芒果"],
    "pineapple": ["pineapple", "Ananas comosus", "菠萝", "凤梨"],
    "passion_fruit": ["passion fruit", "Passiflora edulis", "百香果"],
    "avocado": ["avocado", "Persea americana", "牛油果"],
    "sugar_apple": ["sugar apple", "Annona squamosa", "番荔枝"],
    "guava": ["guava", "Psidium guajava", "番石榴"],
    "rambutan": ["rambutan", "Nephelium lappaceum", "红毛丹"],
    "wampee": ["wampee", "Clausena lansium", "黄皮"],
    "dragon_fruit": ["dragon fruit", "pitaya", "Selenicereus undatus", "Hylocereus", "火龙果"],
    "litchi": ["litchi", "lychee", "Litchi chinensis", "荔枝"],
    "durian": ["durian", "Durio zibethinus", "榴莲"],
    "longan": ["longan", "Dimocarpus longan", "龙眼", "桂圆"],
    "cashew": ["cashew", "Anacardium occidentale", "腰果"],
}

def norm(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()

def pattern(values: list[str]) -> re.Pattern[str]:
    return re.compile("|".join(sorted((re.escape(v) for v in values if v), key=len, reverse=True)), re.I)

def read_catalog(path: Path):
    result = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            aliases = [row["metabolite"], *row.get("synonyms", "").split("|")]
            result.append({"species": row["species"], "name": row["metabolite"], "aliases": [x.strip() for x in aliases if x.strip()]})
    return result

def iter_jsonl(path: Path):
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, 1):
            try: row = json.loads(line)
            except json.JSONDecodeError: continue
            question = norm(row.get("instruction") or row.get("question"))
            answer = norm(row.get("output") or row.get("answer"))
            text = "\n".join(x for x in (question, norm(row.get("input")), answer) if x)
            if text: yield {"text": text, "question": question, "answer": answer, "source": f"{path}:{line_no}", "pmid": norm(row.get("pmid")), "doi": norm(row.get("doi"))}

def iter_table(path: Path):
    if path.suffix.lower() == ".xlsx":
        from openpyxl import load_workbook
        book = load_workbook(path, read_only=True, data_only=True)
        for sheet in book.worksheets:
            rows = sheet.iter_rows(values_only=True); headers = next(rows, None)
            if not headers: continue
            headers = [norm(x).casefold() for x in headers]
            for number, values in enumerate(rows, 2):
                row = {headers[i]: norm(v) for i, v in enumerate(values) if i < len(headers)}
                text = "\n".join(v for v in row.values() if v)
                if text: yield {"text": text, "question": "", "answer": text, "source": f"{path}#{sheet.title}:{number}", "pmid": row.get("pmid", ""), "doi": row.get("doi", "")}
        book.close(); return
    delimiter = "\t" if path.suffix.lower() in {".tsv", ".txt"} else ","
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
        for number, row in enumerate(csv.DictReader(handle, delimiter=delimiter), 2):
            text = "\n".join(norm(v) for v in row.values() if norm(v))
            if text: yield {"text": text, "question": "", "answer": text, "source": f"{path}:{number}", "pmid": norm(row.get("PMID") or row.get("pmid")), "doi": norm(row.get("DOI") or row.get("doi"))}

def iter_pubtator(path: Path):
    with path.open(encoding="utf-8", errors="replace") as handle:
      for line_no, line in enumerate(handle, 1):
        try: raw = json.loads(line)
        except json.JSONDecodeError: continue
        documents = raw.get("documents", [raw])
        for doc in documents:
            pmid = norm(doc.get("id")); passages = doc.get("passages", [])
            text = " ".join(norm(p.get("text")) for p in passages)
            chemicals = []
            for p in passages:
                for ann in p.get("annotations", []):
                    if str(ann.get("infons", {}).get("type", "")).casefold() == "chemical": chemicals.append(norm(ann.get("text")))
            if text: yield {"text": text, "answer": text, "question": "", "source": f"{path}:{line_no}; PubTator PMID:{pmid}", "pmid": pmid, "doi": "", "chemicals": chemicals}

def stable_id(species: str, metabolite: str, source: str) -> str:
    return "met-" + hashlib.sha1(f"{species}\t{metabolite}\t{source}".encode()).hexdigest()[:18]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True); ap.add_argument("--qa", action="append", default=[])
    ap.add_argument("--literature", action="append", default=[]); ap.add_argument("--pubtator", action="append", default=[])
    ap.add_argument("--output-db", required=True); ap.add_argument("--output-qa", required=True)
    ap.add_argument("--audit", required=True); ap.add_argument("--strict", action="store_true")
    args = ap.parse_args(); catalog = read_catalog(Path(args.catalog))
    catalog_patterns = {(x["species"], x["name"]): pattern(x["aliases"]) for x in catalog}
    species_patterns = {key: pattern(values) for key, values in SPECIES.items()}
    records = []
    for value in args.qa: records.extend(iter_jsonl(Path(value)))
    for value in args.literature: records.extend(iter_table(Path(value)))
    for value in args.pubtator: records.extend(iter_pubtator(Path(value)))

    # PubTator annotations expand the seed catalog. This is how metabolites
    # beyond the bundled examples enter both QA and RAG without hand-coding.
    known = {(x["species"], x["name"].casefold()) for x in catalog}
    for record in records:
        chemicals = [x for x in record.get("chemicals", []) if len(x) >= 3]
        if not chemicals: continue
        record_species = [key for key, rx in species_patterns.items() if rx.search(record["text"])]
        for species in record_species:
            for chemical in chemicals:
                key = (species, chemical.casefold())
                if key not in known:
                    catalog.append({"species":species,"name":chemical,"aliases":[chemical]}); known.add(key)
    catalog_patterns = {(x["species"], x["name"]): pattern(x["aliases"]) for x in catalog}

    output = Path(args.output_db); output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists(): output.unlink()
    db = sqlite3.connect(output)
    db.executescript("""
    CREATE TABLE passages(passage_id TEXT PRIMARY KEY,species TEXT,metabolite TEXT,title TEXT,text TEXT,source TEXT,pmid TEXT,doi TEXT,payload_json TEXT);
    CREATE VIRTUAL TABLE passages_fts USING fts5(passage_id UNINDEXED,species,metabolite,title,text,source UNINDEXED,tokenize='trigram');
    CREATE TABLE kg_edges(entity_a TEXT,relation TEXT,entity_b TEXT,passage_id TEXT,weight REAL DEFAULT 1.0);
    CREATE INDEX kg_a ON kg_edges(entity_a); CREATE INDEX kg_b ON kg_edges(entity_b);
    """)
    qa_rows, coverage, seen = [], defaultdict(int), set()
    for record in records:
        text = record["text"]
        found_species = [key for key, rx in species_patterns.items() if rx.search(text)]
        for item in catalog:
            key = (item["species"], item["name"])
            if not catalog_patterns[key].search(text): continue
            species = item["species"]
            # Species-specific evidence is preferred. A record without an explicit
            # species is kept only when it came from an already species-scoped QA.
            if found_species and species not in found_species: continue
            pid = stable_id(species, item["name"], record["source"])
            if pid in seen: continue
            seen.add(pid); title = record["question"] or f"{item['name']} evidence in {species}"
            payload = {"species":species,"metabolite":item["name"],"pmid":record["pmid"],"doi":record["doi"],"source":record["source"]}
            db.execute("INSERT INTO passages VALUES(?,?,?,?,?,?,?,?,?)",(pid,species,item["name"],title,text,record["source"],record["pmid"],record["doi"],json.dumps(payload,ensure_ascii=False)))
            index_text = text + "\nMetabolite aliases: " + " | ".join(item["aliases"]) + "\nSpecies aliases: " + " | ".join(SPECIES.get(species, []))
            db.execute("INSERT INTO passages_fts VALUES(?,?,?,?,?,?)",(pid,species,item["name"],title,index_text,record["source"]))
            for a,r,b,w in [(species,"has_metabolite",item["name"],3.0),(item["name"],"supported_by",record["pmid"] or record["doi"] or record["source"],2.0)]: db.execute("INSERT INTO kg_edges VALUES(?,?,?,?,?)",(a,r,b,pid,w))
            answer = record["answer"] or text
            citation = "; ".join(x for x in [f"PMID {record['pmid']}" if record['pmid'] else "",f"DOI {record['doi']}" if record['doi'] else "",record["source"]] if x)
            qa_rows.append({"instruction":f"What evidence is available for {item['name']} in {species.replace('_',' ')}?","input":"","output":f"{answer}\nEvidence source: {citation}","metadata":payload})
            coverage[key] += 1
    db.commit(); db.close()
    qa_path = Path(args.output_qa); qa_path.parent.mkdir(parents=True,exist_ok=True)
    with qa_path.open("w",encoding="utf-8") as handle:
        for row in qa_rows: handle.write(json.dumps(row,ensure_ascii=False)+"\n")
    missing = [{"species":s,"metabolite":m} for s,m in catalog_patterns if coverage[(s,m)] == 0]
    audit = {"source_records":len(records),"rag_passages":len(seen),"generated_qa":len(qa_rows),"catalog_entries":len(catalog),"covered_entries":len(catalog)-len(missing),"missing":missing,"coverage":{"%s|%s"%k:v for k,v in coverage.items()}}
    Path(args.audit).write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(audit,ensure_ascii=False,indent=2))
    if args.strict and missing: raise SystemExit(f"STRICT COVERAGE FAILED: {len(missing)} metabolites have no evidence")

if __name__ == "__main__": main()
