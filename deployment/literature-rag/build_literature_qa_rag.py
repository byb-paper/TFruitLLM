#!/usr/bin/env python3
"""Build a source-grounded, multi-topic QA and RAG layer for 13 fruit species.

The source workbooks are never modified. Every bibliographic record is placed
in RAG, even if no topic rule matches it. QA summaries are generated only from
records with a PMID/DOI/source locator. Titles are treated as bibliographic
evidence, not as proof of experimental findings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

SPECIES = {
    "mango": ("芒果", ["mango", "Mangifera indica", "芒果"]),
    "pineapple": ("菠萝", ["pineapple", "Ananas comosus", "菠萝", "凤梨"]),
    "passion_fruit": ("百香果", ["passion fruit", "Passiflora edulis", "百香果"]),
    "avocado": ("牛油果", ["avocado", "Persea americana", "牛油果"]),
    "sugar_apple": ("番荔枝", ["sugar apple", "Annona squamosa", "番荔枝"]),
    "guava": ("番石榴", ["guava", "Psidium guajava", "番石榴"]),
    "rambutan": ("红毛丹", ["rambutan", "Nephelium lappaceum", "红毛丹"]),
    "wampee": ("黄皮", ["wampee", "Clausena lansium", "黄皮"]),
    "dragon_fruit": ("火龙果", ["dragon fruit", "pitaya", "Hylocereus", "Selenicereus", "火龙果"]),
    "litchi": ("荔枝", ["litchi", "lychee", "Litchi chinensis", "荔枝"]),
    "durian": ("榴莲", ["durian", "Durio zibethinus", "榴莲"]),
    "longan": ("龙眼", ["longan", "Dimocarpus longan", "龙眼", "桂圆"]),
    "cashew": ("腰果", ["cashew", "Anacardium occidentale", "腰果"]),
}
FOLDER_TO_KEY = {zh: key for key, (zh, _) in SPECIES.items()}


def norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def stable_id(*parts: str) -> str:
    return "lit-" + hashlib.sha1("\t".join(parts).encode("utf-8")).hexdigest()[:20]


def compile_taxonomy(path: Path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    compiled = {}
    for key, value in raw.items():
        words = sorted((norm(x) for x in value["keywords"] if norm(x)), key=len, reverse=True)
        compiled[key] = {
            **value,
            "regex": re.compile("|".join(re.escape(x) for x in words), re.I),
        }
    return raw, compiled


def find_header(rows: list[tuple]) -> tuple[int, dict[str, int]] | None:
    for idx, row in enumerate(rows[:25]):
        cells = [norm(x).casefold() for x in row]
        mapping = {}
        for col, cell in enumerate(cells):
            if cell in {"pmid", "pubmed id"}: mapping["pmid"] = col
            elif cell == "doi": mapping["doi"] = col
            elif "标题" in cell or cell in {"title", "article title"}: mapping["title"] = col
            elif "摘要" in cell or cell == "abstract": mapping["abstract"] = col
            elif "期刊" in cell or cell == "journal": mapping["journal"] = col
            elif "年份" in cell or cell in {"year", "date"}: mapping["year"] = col
        if "title" in mapping and ("pmid" in mapping or "doi" in mapping):
            return idx, mapping
    return None


def iter_workbook(path: Path, species: str, source_name: str = "") -> Iterable[dict]:
    from openpyxl import load_workbook
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        for sheet in book.worksheets:
            rows = list(sheet.iter_rows(values_only=True))
            found = find_header(rows)
            if not found: continue
            header_idx, columns = found
            for excel_row, values in enumerate(rows[header_idx + 1 :], header_idx + 2):
                def get(name: str) -> str:
                    col = columns.get(name)
                    return norm(values[col]) if col is not None and col < len(values) else ""
                title = get("title")
                if not title: continue
                source = f"{source_name or path.name}#{sheet.title}:{excel_row}"
                yield {
                    "species": species,
                    "title": title,
                    "abstract": get("abstract"),
                    "journal": get("journal"),
                    "year": get("year"),
                    "pmid": get("pmid"),
                    "doi": get("doi"),
                    "source": source,
                    "source_type": "literature_workbook",
                }
    finally:
        book.close()


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, 1):
            try: row = json.loads(line)
            except json.JSONDecodeError: continue
            question = norm(row.get("instruction") or row.get("question"))
            answer = norm(row.get("output") or row.get("answer"))
            text = "\n".join(x for x in (question, norm(row.get("input")), answer) if x)
            if not text: continue
            species = detect_species(text)
            yield {
                "species": species[0] if len(species) == 1 else "",
                "title": question or "Existing QA evidence",
                "abstract": answer or text,
                "journal": "", "year": "",
                "pmid": norm(row.get("pmid")), "doi": norm(row.get("doi")),
                "source": f"{path}:{line_no}", "source_type": "qa_jsonl",
            }


def detect_species(text: str) -> list[str]:
    result = []
    for key, (_, aliases) in SPECIES.items():
        if any(re.search(re.escape(alias), text, re.I) for alias in aliases): result.append(key)
    return result


def topic_keys(text: str, taxonomy) -> list[str]:
    return [key for key, value in taxonomy.items() if value["regex"].search(text)]


def extract_entities(text: str) -> dict[str, list[str]]:
    accessions = re.findall(r"\b(?:PRJNA|PRJEB|SRR|ERR|DRR|GCA_|GCF_)[A-Za-z0-9_.-]+\b", text, re.I)
    gene_candidates = re.findall(r"\b(?:LOC\d+|[A-Z][A-Z0-9-]{2,11}\d[A-Z0-9-]*)\b", text)
    return {
        "accessions": list(dict.fromkeys(accessions))[:30],
        "candidate_gene_identifiers": list(dict.fromkeys(gene_candidates))[:30],
    }


def cite(record: dict) -> str:
    values = []
    if record["pmid"]: values.append(f"PMID {record['pmid']}")
    if record["doi"]: values.append(f"DOI {record['doi']}")
    values.append(record["source"])
    return "; ".join(values)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--literature-root", required=True)
    parser.add_argument("--taxonomy", required=True)
    parser.add_argument("--qa", action="append", default=[])
    parser.add_argument("--output-db", required=True)
    parser.add_argument("--output-qa", required=True)
    parser.add_argument("--audit", required=True)
    parser.add_argument("--max-papers-per-summary", type=int, default=20)
    parser.add_argument("--max-unclassified-rate", type=float, default=0.15)
    args = parser.parse_args()

    taxonomy_raw, taxonomy = compile_taxonomy(Path(args.taxonomy))
    records = []
    root = Path(args.literature_root)
    workbook_files = []
    for path in sorted(root.rglob("*.xlsx")):
        if "30年PubMed文献" not in path.name: continue
        species = FOLDER_TO_KEY.get(path.parent.name)
        if not species: continue
        source_name = path.relative_to(root).as_posix()
        workbook_files.append(source_name)
        records.extend(iter_workbook(path, species, source_name))
    for value in args.qa:
        records.extend(iter_jsonl(Path(value)))

    output_db = Path(args.output_db)
    output_db.parent.mkdir(parents=True, exist_ok=True)
    if output_db.exists(): output_db.unlink()
    db = sqlite3.connect(output_db)
    db.executescript("""
    CREATE TABLE passages(
      passage_id TEXT PRIMARY KEY, species TEXT, topics TEXT, title TEXT,
      text TEXT, source TEXT, pmid TEXT, doi TEXT, source_type TEXT,
      entities_json TEXT, payload_json TEXT
    );
    CREATE VIRTUAL TABLE passages_fts USING fts5(
      passage_id UNINDEXED, species, topics, title, text, source UNINDEXED,
      tokenize='trigram'
    );
    CREATE TABLE kg_edges(entity_a TEXT, relation TEXT, entity_b TEXT,
      passage_id TEXT, weight REAL DEFAULT 1.0);
    CREATE INDEX kg_a ON kg_edges(entity_a);
    CREATE INDEX kg_b ON kg_edges(entity_b);
    """)

    counts = Counter()
    species_counts = Counter()
    cross = Counter()
    groups = defaultdict(list)
    unclassified = []
    seen = set()
    for record in records:
        text = "\n".join(x for x in (record["title"], record["abstract"]) if x)
        topics = topic_keys(text, taxonomy)
        indexed_topics = topics or ["other_unclassified"]
        pid = stable_id(record["species"], record["pmid"] or record["doi"] or record["title"], record["source"])
        if pid in seen: continue
        seen.add(pid)
        entities = extract_entities(text)
        payload = {k: record[k] for k in ("species", "pmid", "doi", "source", "source_type")}
        payload["topics"] = indexed_topics
        row = (pid, record["species"], "|".join(indexed_topics), record["title"], text,
               record["source"], record["pmid"], record["doi"], record["source_type"],
               json.dumps(entities, ensure_ascii=False), json.dumps(payload, ensure_ascii=False))
        db.execute("INSERT INTO passages VALUES(?,?,?,?,?,?,?,?,?,?,?)", row)
        aliases = " | ".join(SPECIES.get(record["species"], ("", []))[1])
        topic_labels = " | ".join(taxonomy_raw.get(x, {}).get("label_zh", x) for x in indexed_topics)
        db.execute("INSERT INTO passages_fts VALUES(?,?,?,?,?,?)",
                   (pid, record["species"] + " " + aliases, "|".join(indexed_topics) + " " + topic_labels,
                    record["title"], text, record["source"]))
        species_counts[record["species"] or "species_unspecified"] += 1
        for topic in indexed_topics:
            counts[topic] += 1
            cross[(record["species"] or "species_unspecified", topic)] += 1
            groups[(record["species"], topic)].append(record)
            db.execute("INSERT INTO kg_edges VALUES(?,?,?,?,?)", (record["species"] or "species_unspecified", "has_literature_topic", topic, pid, 2.0))
        for accession in entities["accessions"]:
            db.execute("INSERT INTO kg_edges VALUES(?,?,?,?,?)", (record["species"] or "species_unspecified", "has_accession_evidence", accession, pid, 2.0))
        if not topics:
            unclassified.append({"species": record["species"], "title": record["title"], "pmid": record["pmid"], "doi": record["doi"], "source": record["source"]})
    db.commit()
    db.close()

    qa_rows = []
    for (species, topic), evidence in sorted(groups.items()):
        if not species or topic == "other_unclassified": continue
        label = taxonomy_raw[topic]["label_zh"]
        chosen = evidence[: args.max_papers_per_summary]
        lines = []
        for idx, record in enumerate(chosen, 1):
            lines.append(f"{idx}. {record['title']}（{cite(record)}）")
        note = "以下是文献题名层面的可追溯证据；若原表没有摘要，不能仅凭题名推断具体实验结论。"
        output = note + "\n" + "\n".join(lines)
        qa_rows.append({
            "instruction": f"{SPECIES[species][0]}在“{label}”方面有哪些文献证据？",
            "input": "",
            "output": output,
            "metadata": {"species": species, "topic": topic, "evidence_count": len(evidence), "shown": len(chosen)},
        })
    output_qa = Path(args.output_qa)
    output_qa.parent.mkdir(parents=True, exist_ok=True)
    with output_qa.open("w", encoding="utf-8") as handle:
        for row in qa_rows: handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    literature_records = sum(1 for r in records if r["source_type"] == "literature_workbook")
    unclassified_lit = sum(1 for r in unclassified if "#" in r["source"])
    rate = unclassified_lit / literature_records if literature_records else 0.0
    audit = {
        "workbooks": workbook_files,
        "source_records": len(records),
        "literature_records": literature_records,
        "rag_passages": len(seen),
        "generated_grouped_qa": len(qa_rows),
        "topic_counts_multi_label": dict(counts),
        "species_counts": dict(species_counts),
        "species_topic_counts": {f"{species}|{topic}": count for (species, topic), count in sorted(cross.items())},
        "unclassified_literature_count": unclassified_lit,
        "unclassified_literature_rate": round(rate, 6),
        "unclassified_examples": unclassified[:100],
        "coverage_note": "Counts are bibliographic coverage, not proof that every possible study or metabolite has been captured.",
    }
    Path(args.audit).write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: audit[k] for k in ("literature_records", "rag_passages", "generated_grouped_qa", "topic_counts_multi_label", "unclassified_literature_rate")}, ensure_ascii=False, indent=2))
    if rate > args.max_unclassified_rate:
        raise SystemExit(f"AUDIT FAILED: unclassified literature rate {rate:.2%} exceeds {args.max_unclassified_rate:.2%}")


if __name__ == "__main__":
    main()
