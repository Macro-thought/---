# -*- coding: utf-8 -*-
"""Draw the 20-question review sheet required by T2.2, with the evidence text
that a human would need, so the answerability judgement is not a guess.
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
    sample = qs[::6][:20]
    rows = []
    for q in sample:
        spec = q["query"]
        ev = []
        if spec["qt"] == "referral":
            for i in g.resolve(spec["subject"]):
                ev.append("【%s】%s" % (g.label(i), docs.get(i, "")))
        else:
            ids = g.uset(spec) if spec["qt"] == "universal" else g.scope(spec["type"], spec.get("country"))
            for i in sorted(ids)[:3]:
                ev.append("【%s】%s" % (g.label(i), docs.get(i, "")))
            ev.append("……（同类共 %d 个实体）" % len(ids))
        rows.append({
            "qid": q["qid"], "question": q["question"], "answer_type": q["answer_type"],
            "gold_v1": q["gold_v1_text"], "evidence": ev,
        })

    lines = ["# T2.2 二十题可答性复核", "",
             "判据：一个了解业务的人只凭语料能否答出。计数题需要遍历同类全部实体，"
             "属于「语料完备但 top-k 检索无法聚合」的情形，记为可答但在冒烟里单独统计。", ""]
    for n, r in enumerate(rows, 1):
        lines.append("## %d. %s" % (n, r["qid"]))
        lines.append("- 问：%s" % r["question"])
        lines.append("- 类型：%s　gold(v1)：%s" % (r["answer_type"], r["gold_v1"]))
        lines.append("- 证据：")
        for e in r["evidence"]:
            lines.append("  - " + e)
        lines.append("")
    (BASE / "qa" / "review_sample.md").write_text("\n".join(lines), encoding="utf-8")
    print("rows", len(rows))


if __name__ == "__main__":
    main()
