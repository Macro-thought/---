# -*- coding: utf-8 -*-
"""T2.2 answerability audit.

For every question, check that the facts needed to answer it are present in the
corpus built from G_v1:
* referral   -> the subject document names every gold hub;
* count / universal -> every entity in scope has a document, and for scoped
  questions its document names the country.
This is a necessary condition, not a retrieval test: top-k RAG still has to find
the documents, and counts still require aggregation. The distinction is recorded
in the report.
"""
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "labels"))
from solver import G, load  # noqa: E402

COUNTRY_SHORT = {"Q148": "中国", "Q17": "日本", "Q865": "台湾地区", "Q884": "韩国"}


def main():
    g = G(load(BASE / "data" / "graph_v1.json"))
    docs = {}
    for line in open(BASE / "corpus" / "corpus.jsonl", encoding="utf-8"):
        d = json.loads(line)
        docs[d["entity_id"]] = d["text"]

    qs = [json.loads(l) for l in open(BASE / "qa" / "questions.jsonl", encoding="utf-8")]
    texts = {}
    for q in qs:
        texts.setdefault(q["question"], []).append(q["qid"])

    rows, ok = [], 0
    for q in qs:
        spec = q["query"]
        reasons = []
        if spec["qt"] == "referral":
            subj = g.resolve(spec["subject"])
            if not subj:
                reasons.append("subject not resolvable")
            for i in subj:
                if i not in docs:
                    reasons.append("no doc for %s" % i)
            for t in (q["gold_v1"] if isinstance(q["gold_v1"], list) else []):
                name = g.label(t)
                if not any(name in docs.get(i, "") for i in subj):
                    reasons.append("hub %s not mentioned in subject doc" % name)
        else:
            ids = g.uset(spec) if spec["qt"] == "universal" else g.scope(spec["type"], spec.get("country"))
            if not ids:
                reasons.append("empty scope")
            missing = [i for i in ids if i not in docs]
            if missing:
                reasons.append("missing docs: %d" % len(missing))
            c = spec.get("country")
            if c:
                cname = COUNTRY_SHORT.get(c)
                bad = [i for i in ids if cname and cname not in docs.get(i, "")]
                if bad:
                    reasons.append("country not stated in %d docs" % len(bad))
        if not reasons:
            ok += 1
        rows.append({"qid": q["qid"], "answerable": not reasons, "issues": reasons})

    dup = {t: v for t, v in texts.items() if len(v) > 1}
    stats = {"n": len(qs), "answerable": ok, "rate": round(ok / len(qs), 3),
             "duplicate_questions": dup}
    (BASE / "qa" / "answerability.json").write_text(
        json.dumps({"stats": stats, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: stats[k] for k in ("n", "answerable", "rate")}, ensure_ascii=False))
    print("dup groups:", len(dup))


if __name__ == "__main__":
    main()
