# -*- coding: utf-8 -*-
"""B2 graph retrieval: 2-hop subgraph around the entities named in the question,
verbalised into triples, then the same reader. Unlike B1 this baseline *reads
the graph*, so a schema change is supposed to move it.
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (BASE, read_answer, run)  # noqa: E402


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default=str(BASE / "qa" / "questions.jsonl"))
    ap.add_argument("--graph", default=str(BASE / "data" / "graph_v1.json"))
    ap.add_argument("--out", default=str(BASE / "baselines" / "out" / "b2_v1.json"))
    ap.add_argument("--hops", type=int, default=2)
    args = ap.parse_args()

    g = load(args.graph)
    nodes = {n["id"]: n for n in g["entities"]}
    out = defaultdict(list)
    inn = defaultdict(list)
    for e in g["edges"]:
        out[e["h"]].append(e)
        inn[e["t"]].append(e)

    names = [n["label_zh"] for n in g["entities"]] + \
            [a for n in g["entities"] for a in n.get("aliases", [])]
    names = list(dict.fromkeys(names))

    def seed_ids(question):
        ids = []
        for name in sorted(names, key=len, reverse=True):
            if name and name in question:
                for n in g["entities"]:
                    if n["label_zh"] == name or name in n.get("aliases", []):
                        ids.append(n["id"])
                break
        return ids

    def verbalise(q):
        seeds = seed_ids(q["question"])
        seen, frontier = set(seeds), set(seeds)
        for _ in range(args.hops):
            nxt = set()
            for i in frontier:
                for e in out.get(i, []) + inn.get(i, []):
                    nxt.add(e["h"])
                    nxt.add(e["t"])
            frontier = nxt - seen
            seen |= nxt
            if not frontier:
                break
        lines = []
        for i in seen:
            for e in out.get(i, []):
                if e["t"] in seen:
                    lines.append("%s的%s是%s。" % (
                        nodes[e["h"]]["label_zh"], e["rel"], nodes[e["t"]]["label_zh"]))
        return "".join(lines), len(seen)

    def answer(q):
        ctx, _ = verbalise(q)
        return read_answer(q["question"], ctx, names, triple_mode=True), ctx

    qs = [json.loads(l) for l in open(args.questions, encoding="utf-8")]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    rows, dt = run(qs, answer, Path(args.out), "B2_graph",
                   {"graph": str(Path(args.graph).name), "hops": args.hops,
                    "reader": "extractive placeholder"})
    print("B2 answers", len(rows), "elapsed", round(dt, 2))


if __name__ == "__main__":
    main()
