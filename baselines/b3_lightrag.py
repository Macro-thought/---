# -*- coding: utf-8 -*-
"""B3 LightRAG baseline.

Two modes:

  probe (default)  Check whether the real `lightrag` package is importable and
                   write baselines/out/b3_status.json. LightRAG additionally
                   needs an LLM endpoint for entity/relation extraction and for
                   answering, so a missing key is recorded as a blocking reason
                   even if the package happens to be installed.

  --proxy          Run a *local stand-in* for LightRAG's dual-level retrieval:
                   low level = top-k text chunks (same corpus index as B1),
                   high level = 2-hop verbalised triples around question
                   entities (same expansion as B2). This is NOT LightRAG and the
                   output file name says proxy; it exists only so the pipeline
                   has a third column when the real system cannot be run here.

The status file is the honest record: if it says available=false, no real
LightRAG numbers exist and none are reported as such anywhere else.
"""
import argparse
import importlib.util
import json
import os
import platform
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (BASE, Index, load_corpus, read_answer, run)  # noqa: E402


def probe(out_dir):
    spec = importlib.util.find_spec("lightrag")
    reasons = []
    if spec is None:
        reasons.append("python package 'lightrag' is not installed")
    key_vars = ["OPENAI_API_KEY", "DASHSCOPE_API_KEY", "QWEN_API_KEY", "LLM_API_KEY"]
    present = [k for k in key_vars if os.environ.get(k)]
    if not present:
        reasons.append("no LLM API key in environment (%s)" % ", ".join(key_vars))
    status = {
        "system": "B3_LightRAG",
        "available": spec is not None and bool(present),
        "package_found": spec is not None,
        "package_origin": getattr(spec, "origin", None) if spec else None,
        "llm_keys_present": present,
        "python": platform.python_version(),
        "executable": sys.executable,
        "blocking_reasons": reasons,
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "consequence": ("No real LightRAG answer is produced in this run. "
                        "Run `python baselines/b3_lightrag.py --proxy` for the "
                        "clearly-labelled local stand-in, or install lightrag and "
                        "export an API key, then rerun without --proxy."),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "b3_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    print("B3 available=%s reasons=%s" % (status["available"], reasons))
    return status


def proxy(args):
    docs = load_corpus()
    index = Index(docs)
    g = json.load(open(args.graph, encoding="utf-8"))
    nodes = {n["id"]: n for n in g["entities"]}
    out_adj, inn_adj = defaultdict(list), defaultdict(list)
    for e in g["edges"]:
        out_adj[e["h"]].append(e)
        inn_adj[e["t"]].append(e)
    names = list(dict.fromkeys(
        [n["label_zh"] for n in g["entities"]] +
        [a for n in g["entities"] for a in n.get("aliases", [])]))

    def seeds(question):
        for name in sorted(names, key=len, reverse=True):
            if name and name in question:
                ids = [n["id"] for n in g["entities"]
                       if n["label_zh"] == name or name in n.get("aliases", [])]
                if ids:
                    return ids
        return []

    def triples(question):
        seen, frontier = set(seeds(question)), set(seeds(question))
        for _ in range(args.hops):
            nxt = set()
            for i in frontier:
                for e in out_adj.get(i, []) + inn_adj.get(i, []):
                    nxt.update((e["h"], e["t"]))
            frontier = nxt - seen
            seen |= nxt
            if not frontier:
                break
        lines = []
        for i in seen:
            for e in out_adj.get(i, []):
                if e["t"] in seen:
                    lines.append("%s的%s是%s。" % (
                        nodes[e["h"]]["label_zh"], e["rel"], nodes[e["t"]]["label_zh"]))
        return "".join(lines)

    def answer(q):
        low = "".join(d["text"] for _, d in index.search(q["question"], args.k))
        high = triples(q["question"])
        ctx = low + high
        return read_answer(q["question"], ctx, names, triple_mode=True), ctx

    qs = [json.loads(l) for l in open(args.questions, encoding="utf-8")]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    rows, dt = run(qs, answer, Path(args.out), "B3_proxy",
                   {"warning": "local hybrid stand-in, NOT real LightRAG",
                    "graph": Path(args.graph).name, "k": args.k, "hops": args.hops,
                    "reader": "extractive placeholder"})
    print("B3 proxy answers", len(rows), "elapsed", round(dt, 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default=str(BASE / "qa" / "questions.jsonl"))
    ap.add_argument("--graph", default=str(BASE / "data" / "graph_v1.json"))
    ap.add_argument("--out", default=str(BASE / "baselines" / "out" / "b3_proxy_v1.json"))
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--hops", type=int, default=2)
    ap.add_argument("--proxy", action="store_true")
    args = ap.parse_args()
    if args.proxy:
        proxy(args)
        return
    probe(Path(args.out).parent)


if __name__ == "__main__":
    main()
