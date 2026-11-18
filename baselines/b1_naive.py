# -*- coding: utf-8 -*-
"""B1 naive RAG: fixed corpus, vector top-k, extractive reader.

This baseline never reads the graph, so a schema change should barely move it.
It is the empty control that separates graph-layer flips from text-layer noise.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (BASE, Index, load_corpus, read_answer, run)  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default=str(BASE / "qa" / "questions.jsonl"))
    ap.add_argument("--out", default=str(BASE / "baselines" / "out" / "b1_v1.json"))
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()

    g = json.load(open(BASE / "data" / "graph_v1.json", encoding="utf-8"))
    names = [n["label_zh"] for n in g["entities"]] + \
            [a for n in g["entities"] for a in n.get("aliases", [])]
    names = list(dict.fromkeys(names))

    docs = load_corpus()
    index = Index(docs)

    def answer(q):
        hits = index.search(q["question"], args.k)
        context = "".join(d["text"] for _, d in hits)
        return read_answer(q["question"], context, names), context

    qs = [json.loads(l) for l in open(args.questions, encoding="utf-8")]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    rows, dt = run(qs, answer, Path(args.out), "B1_naive",
                   {"retriever": "char-bigram tfidf", "k": args.k,
                    "reader": "extractive placeholder"})
    print("B1 answers", len(rows), "elapsed", round(dt, 2))


if __name__ == "__main__":
    main()
