# -*- coding: utf-8 -*-
"""Score baseline answer files against the solver labels.

For every system we compare the answer on G_v1 with the answer on G_op and ask
whether the *system's answer* changed, then cross-tabulate that against the
solver's expected flip:

  FR  (flip rate)        = observed answer change rate
  FFR (false flip rate)  = P(observed flip | gold stable)
  MFR (missed flip rate) = P(observed stable | gold flip)

The baselines use an extractive placeholder reader, so the numbers say how the
*retrieval context* moves under a schema change, not how a tuned LLM would
answer. eval/scores.md says this explicitly at the top.
"""
import json
import re
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "eval"
OPS = ["add_inst", "refine_type", "restrict_rel", "merge_entity", "split_concept"]
QT = ["referral", "count", "universal"]
CN = {"referral": "指称", "count": "计数", "universal": "全称"}
OPCN = {"add_inst": "ADD_INST", "refine_type": "REFINE_TYPE", "restrict_rel": "RESTRICT_REL",
        "merge_entity": "MERGE_ENTITY", "split_concept": "SPLIT_CONCEPT"}


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")]


def load_answers(p):
    d = json.load(open(p, encoding="utf-8"))
    return {r["qid"]: r for r in d["answers"]}, d


def name_map(graph):
    m = {}
    for n in graph["entities"]:
        for name in [n["label_zh"]] + n.get("aliases", []):
            m[name] = n["id"]
    return m


def canon_referral(text, n2i):
    text = (text or "").strip()
    if not text:
        return frozenset()
    toks = [t.strip() for t in re.split(r"[、，,;；\s]+", text) if t.strip()]
    out = []
    for t in toks:
        if t in n2i:
            out.append(n2i[t])
            continue
        hit = None
        for name in sorted(n2i, key=len, reverse=True):
            if name in t:
                hit = n2i[name]
                break
        out.append(hit if hit else t)
    return frozenset(out)


def canon_gold(q, key, n2i):
    g = q[key]
    if q["qtype"] == "referral":
        return frozenset(g)
    return g


def canon_answer(q, text, n2i):
    if q["qtype"] == "referral":
        return canon_referral(text, n2i)
    if q["qtype"] == "count":
        m = re.search(r"-?\d+", text or "")
        return int(m.group()) if m else None
    t = (text or "").strip()
    if t.startswith("是"):
        return True
    if t.startswith("否"):
        return False
    return t


def assess(rows1, rows2, qs, n2i):
    cells = defaultdict(lambda: dict(n=0, obs_flip=0, gold_flip=0, acc1=0, acc2=0,
                                     false_flip=0, missed_flip=0))
    for q in qs:
        qid = q["qid"]
        a1 = canon_answer(q, rows1[qid]["answer"], n2i)
        a2 = canon_answer(q, rows2[qid]["answer"], n2i)
        g1, g2 = canon_gold(q, "gold_v1", n2i), canon_gold(q, "gold_v2", n2i)
        c = cells[(q["operator"], q["qtype"])]
        c["n"] += 1
        obs = a1 != a2
        gold = g1 != g2
        c["obs_flip"] += obs
        c["gold_flip"] += gold
        c["acc1"] += (a1 == g1)
        c["acc2"] += (a2 == g2)
        c["false_flip"] += (obs and not gold)
        c["missed_flip"] += ((not obs) and gold)
    return cells


def aggregate(cells, op=None):
    tot = dict(n=0, obs_flip=0, gold_flip=0, acc1=0, acc2=0, false_flip=0, missed_flip=0)
    for (opname, _qt), c in cells.items():
        if op is not None and opname != OPCN[op]:
            continue
        for k in tot:
            tot[k] += c[k]
    stable = tot["n"] - tot["gold_flip"]
    return {
        "n": tot["n"],
        "FR": round(tot["obs_flip"] / tot["n"], 3),
        "FFR": round(tot["false_flip"] / stable, 3) if stable else None,
        "MFR": round(tot["missed_flip"] / tot["gold_flip"], 3) if tot["gold_flip"] else None,
        "acc_v1": round(tot["acc1"] / tot["n"], 3),
        "acc_v2": round(tot["acc2"] / tot["n"], 3),
    }


def main():
    qs = load_jsonl(BASE / "qa" / "questions.jsonl")
    labels = {x["qid"]: x for x in json.load(
        open(BASE / "labels" / "labels.json", encoding="utf-8"))}
    for q in qs:
        q["gold_v2"] = labels[q["qid"]]["gold_v2"]
        q["expected"] = labels[q["qid"]]["expected"]
    g1 = json.load(open(BASE / "data" / "graph_v1.json", encoding="utf-8"))
    n2i = name_map(g1)
    OUT.mkdir(exist_ok=True)

    systems = {}
    b1r, _ = load_answers(BASE / "baselines" / "out" / "b1_v1.json")
    b1cells = assess(b1r, b1r, qs, n2i)          # corpus fixed => identical both sides
    systems["B1_naive"] = {op: b1cells for op in OPS}
    r1, _ = load_answers(BASE / "baselines" / "out" / "b2_v1.json")
    systems["B2_graph"] = {op: assess(r1, load_answers(
        BASE / "baselines" / "out" / ("b2_%s.json" % op))[0], qs, n2i) for op in OPS}
    r1, _ = load_answers(BASE / "baselines" / "out" / "b3_proxy_v1.json")
    systems["B3_proxy"] = {op: assess(r1, load_answers(
        BASE / "baselines" / "out" / ("b3_proxy_%s.json" % op))[0], qs, n2i) for op in OPS}

    report = {}
    lines = ["# 基线答案翻转评分", "",
             "读数说明：三个基线都用**抽取式占位阅读器**（无 LLM key），因此下表衡量的是"
             "“检索上下文随模式变化而移动”的程度，不是调优后 LLM 的翻转率。"
             "计数题在占位阅读器下无法聚合，准确率天然为 0，其翻转率只作管线连通性证据。", ""]
    for sysname, per_op in systems.items():
        report[sysname] = {}
        lines.append("## %s" % sysname)
        lines.append("")
        lines.append("| 算子 | 问句类型 | n | 观测翻转 | 应然翻转 | FR | FFR | MFR | acc v1 | acc v2 |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for op in OPS:
            cells = per_op[op]
            for qt in QT:
                c = cells[(OPCN[op], qt)]
                stable = c["n"] - c["gold_flip"]
                fr = c["obs_flip"] / c["n"]
                ffr = c["false_flip"] / stable if stable else None
                mfr = c["missed_flip"] / c["gold_flip"] if c["gold_flip"] else None
                lines.append("| %s | %s | %d | %d | %d | %.3f | %s | %s | %.3f | %.3f |" % (
                    OPCN[op], CN[qt], c["n"], c["obs_flip"], c["gold_flip"], fr,
                    "-" if ffr is None else "%.3f" % ffr,
                    "-" if mfr is None else "%.3f" % mfr,
                    c["acc1"] / c["n"], c["acc2"] / c["n"]))
                report[sysname].setdefault(op, {})[qt] = {
                    "n": c["n"], "obs_flip": c["obs_flip"], "gold_flip": c["gold_flip"],
                    "FR": round(fr, 3), "FFR": None if ffr is None else round(ffr, 3),
                    "MFR": None if mfr is None else round(mfr, 3),
                    "acc_v1": round(c["acc1"] / c["n"], 3),
                    "acc_v2": round(c["acc2"] / c["n"], 3)}
            report[sysname][op]["overall"] = aggregate(cells, op)
        lines.append("")
        for op in OPS:
            agg = report[sysname][op]["overall"]
            lines.append("- %s 总体：FR=%.3f FFR=%s MFR=%s acc_v1=%.3f acc_v2=%.3f" % (
                OPCN[op], agg["FR"],
                "-" if agg["FFR"] is None else "%.3f" % agg["FFR"],
                "-" if agg["MFR"] is None else "%.3f" % agg["MFR"],
                agg["acc_v1"], agg["acc_v2"]))
        lines.append("")

    (OUT / "scores.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    (OUT / "scores.md").write_text("\n".join(lines), encoding="utf-8")

    # compact flip matrix for the report
    m = ["| 算子 | 指称 观测/应然 | 计数 观测/应然 | 全称 观测/应然 |",
         "|---|---|---|---|"]
    for op in OPS:
        row = [OPCN[op]]
        for qt in QT:
            a = report["B2_graph"][op][qt]
            row.append("%d/%d" % (a["obs_flip"], a["gold_flip"]))
        m.append("| " + " | ".join(row) + " |")
    (OUT / "matrix_b2.md").write_text("\n".join(m), encoding="utf-8")
    print("scored systems:", ", ".join(systems))
    print("wrote eval/scores.md eval/scores.json eval/matrix_b2.md")


if __name__ == "__main__":
    main()
