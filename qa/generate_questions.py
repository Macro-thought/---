# -*- coding: utf-8 -*-
"""T1.4 + T1.5: generate the 120-question bank, the gold labels and the 5x3
expected matrix from the deterministic solver.

Sampling rules (fixed before looking at any result):
* referral / count cells: take the first 8 candidates in a deterministic order.
* the SPLIT_CONCEPT universal cell is defined as the "must-flip" cell, i.e. a
  universal over the parent concept that is FALSE in v1. After the split the
  parent has no instance left, so the same universal is vacuously TRUE. The
  candidate list is therefore filtered on `gold_v1 is False` -- that is the
  definition of the cell, not a post-hoc selection on the outcome.
"""
import csv
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "labels"))
from solver import G, load, render, solve_pair  # noqa: E402

GRAPHS = {
    "ADD_INST": BASE / "ops" / "graphs" / "add_inst.json",
    "REFINE_TYPE": BASE / "ops" / "graphs" / "refine_type.json",
    "RESTRICT_REL": BASE / "ops" / "graphs" / "restrict_rel.json",
    "MERGE_ENTITY": BASE / "ops" / "graphs" / "merge_entity.json",
    "SPLIT_CONCEPT": BASE / "ops" / "graphs" / "split_concept.json",
}
COUNTRY_SHORT = {"Q148": "中国", "Q17": "日本", "Q865": "台湾地区", "Q884": "韩国"}
PRIOR = {
    "ADD_INST": {"referral": "稳定", "count": "稳定", "universal": "稳定"},
    "REFINE_TYPE": {"referral": "稳定", "count": "稳定", "universal": "稳定"},
    "RESTRICT_REL": {"referral": "可能翻", "count": "可能翻", "universal": "可能翻"},
    "MERGE_ENTITY": {"referral": "稳定", "count": "必翻", "universal": "可能翻"},
    "SPLIT_CONCEPT": {"referral": "稳定", "count": "可能翻", "universal": "必翻"},
}
MERGE_KEEP = "Q5099568"   # 华航集团 (企业)
MERGE_DROP = "Q51756"     # 中华航空 (航空公司)


# ---------------------------------------------------------------- wording
def count_prefix(q):
    c = q.get("country")
    return "%s的" % COUNTRY_SHORT[c] if c else ""


def uprefix(q):
    if q.get("subject"):
        return "「%s」" % q["subject"]
    c = q.get("country")
    return "所有%s的" % COUNTRY_SHORT[c] if c else "所有"


def utype(q):
    return "" if q.get("subject") else q["type"]


def question_text(q):
    qt = q["qt"]
    if qt == "referral":
        return "「%s」的%s是哪个（些）？" % (q["subject"], q["rel"])
    if qt == "count":
        k = q["kind"]
        cp = count_prefix(q)
        if k == "members":
            c = q.get("country")
            if c:
                return "%s共有多少个%s？" % (COUNTRY_SHORT[c], q["type"])
            return "全图共有多少个%s？" % q["type"]
        if k == "with_rel":
            return "%s%s中，有%s的有多少个？" % (cp, q["type"], q["rel"])
        if k == "rel_to":
            return "%s%s中，%s包含「%s」的有多少个？" % (cp, q["type"], q["rel"], q["target"])
    if qt == "universal":
        k = q["kind"]
        up, ut = uprefix(q), utype(q)
        if k == "all_have_rel":
            return "是否%s%s都有%s？" % (up, ut, q["rel"])
        if k == "all_have_in_rel":
            return "是否%s%s都是某个%s的目标？" % (up, ut, q["rel"])
        if k == "all_target_class":
            return "是否%s%s的%s都是%s？" % (up, ut, q["rel"], q["klass"])
        if k == "all_is":
            return "是否%s%s都是%s？" % (up, ut, q["klass"])
        if k == "all_rel_to":
            return "是否%s%s的%s都包含「%s」？" % (up, ut, q["rel"], q["target"])
        if k == "all_target_have_rel":
            return "是否%s%s的%s对象都有%s？" % (up, ut, q["rel"], q["rel2"])
    raise ValueError("no template for %r" % q)


def answer_type(q):
    return {"referral": "entity_set", "count": "int", "universal": "bool"}[q["qt"]]


# ---------------------------------------------------------------- candidates
def airlines_with_hub(g):
    air = g.members("航空公司")
    ids = {e["h"] for e in g.graph["edges"] if e["rel"] == "枢纽机场"} & air
    return sorted(i for i in ids if g.targets({i}, "枢纽机场"))


def subj(name):
    return {"qt": "referral", "subject": name, "rel": "枢纽机场"}


def build_candidates(g1):
    C = {}
    airlines = [g1.label(i) for i in airlines_with_hub(g1)]
    used_subjects = set()

    def pick_subjects(preferred, n=8):
        out = []
        for a in list(preferred) + airlines:
            if a in used_subjects or a in out:
                continue
            out.append(a)
            if len(out) == n:
                break
        used_subjects.update(out)
        return [subj(a) for a in out]

    # ---- ADD_INST: seed-country scoped, new entities are outside the scope
    C["ADD_INST"] = {
        "referral": pick_subjects([]),
        "count": [
            {"qt": "count", "kind": "members", "type": "航空公司", "country": "Q148"},
            {"qt": "count", "kind": "members", "type": "航空公司", "country": "Q17"},
            {"qt": "count", "kind": "members", "type": "航空公司", "country": "Q865"},
            {"qt": "count", "kind": "members", "type": "航空公司", "country": "Q884"},
            {"qt": "count", "kind": "members", "type": "机场", "country": "Q884"},
            {"qt": "count", "kind": "with_rel", "type": "航空公司", "rel": "运营机型", "country": "Q17"},
            {"qt": "count", "kind": "members", "type": "货运航空", "country": "Q148"},
            {"qt": "count", "kind": "members", "type": "国际机场", "country": "Q17"},
        ],
        "universal": [
            {"qt": "universal", "kind": "all_have_rel", "type": "航空公司", "rel": "国家", "country": "Q148"},
            {"qt": "universal", "kind": "all_have_rel", "type": "航空公司", "rel": "枢纽机场", "country": "Q17"},
            {"qt": "universal", "kind": "all_have_rel", "type": "航空公司", "rel": "枢纽机场", "country": "Q865"},
            {"qt": "universal", "kind": "all_have_rel", "type": "航空公司", "rel": "运营机型", "country": "Q884"},
            {"qt": "universal", "kind": "all_have_rel", "type": "航空公司", "rel": "总部", "country": "Q148"},
            {"qt": "universal", "kind": "all_have_rel", "type": "机场", "rel": "所在行政区", "country": "Q148"},
            {"qt": "universal", "kind": "all_have_rel", "type": "货运航空", "rel": "枢纽机场", "country": "Q17"},
            {"qt": "universal", "kind": "all_have_rel", "type": "机场", "rel": "服务城市", "country": "Q148"},
        ],
    }

    # ---- REFINE_TYPE: parent kept in type_path => membership preserved
    refined = [g1.label(i) for i in airlines_with_hub(g1)
               if g1.nodes[i]["props"].get("p31_subtype") not in (None, "航空公司")]
    plain = [a for a in airlines if a not in refined]
    C["REFINE_TYPE"] = {
        "referral": pick_subjects(refined[:4]),
        "count": [
            {"qt": "count", "kind": "with_rel", "type": "机场", "rel": "所在行政区"},
            {"qt": "count", "kind": "members", "type": "货运航空"},
            {"qt": "count", "kind": "members", "type": "支线航空"},
            {"qt": "count", "kind": "members", "type": "低成本航空"},
            {"qt": "count", "kind": "members", "type": "直升机航空"},
            {"qt": "count", "kind": "with_rel", "type": "航空公司", "rel": "枢纽机场"},
            {"qt": "count", "kind": "members", "type": "固定翼机型"},
            {"qt": "count", "kind": "members", "type": "直升机"},
        ],
        "universal": [
            {"qt": "universal", "kind": "all_is", "type": "航空公司", "klass": "企业"},
            {"qt": "universal", "kind": "all_have_rel", "type": "航空公司", "rel": "国家"},
            {"qt": "universal", "kind": "all_have_rel", "type": "航空公司", "rel": "枢纽机场"},
            {"qt": "universal", "kind": "all_have_rel", "type": "货运航空", "rel": "枢纽机场"},
            {"qt": "universal", "kind": "all_have_rel", "type": "航空公司", "rel": "运营机型"},
            {"qt": "universal", "kind": "all_is", "type": "货运航空", "klass": "航空公司"},
            {"qt": "universal", "kind": "all_target_class", "type": "支线航空", "rel": "枢纽机场", "klass": "国际机场"},
            {"qt": "universal", "kind": "all_have_rel", "type": "直升机航空", "rel": "枢纽机场"},
        ],
    }

    # ---- RESTRICT_REL: 枢纽机场 narrowed to international airports
    g2 = G(load(GRAPHS["RESTRICT_REL"]))
    lost = sorted([i for i in g1.members("航空公司")
                   if g1.targets({i}, "枢纽机场") and not g2.targets({i}, "枢纽机场")])
    kept = sorted([i for i in g1.members("航空公司")
                   if g1.targets({i}, "枢纽机场") and g2.targets({i}, "枢纽机场")])
    lost_free = [g1.label(i) for i in lost if g1.label(i) not in used_subjects]
    kept_free = [g1.label(i) for i in kept if g1.label(i) not in used_subjects]
    r_pick = lost_free[:4] + kept_free[:4]
    used_subjects.update(r_pick)
    C["RESTRICT_REL"] = {
        "referral": [subj(a) for a in r_pick],
        "count": [
            {"qt": "count", "kind": "with_rel", "type": "航空公司", "rel": "枢纽机场", "country": "Q17"},
            {"qt": "count", "kind": "with_rel", "type": "航空公司", "rel": "枢纽机场", "country": "Q148"},
            {"qt": "count", "kind": "with_rel", "type": "航空公司", "rel": "枢纽机场", "country": "Q884"},
            {"qt": "count", "kind": "rel_to", "type": "航空公司", "rel": "枢纽机场", "target": "那霸机场"},
            {"qt": "count", "kind": "members", "type": "机型"},
            {"qt": "count", "kind": "members", "type": "组织"},
            {"qt": "count", "kind": "members", "type": "国家"},
            {"qt": "count", "kind": "members", "type": "机场", "country": "Q17"},
        ],
        "universal": [
            {"qt": "universal", "kind": "all_have_rel", "type": "航空公司", "rel": "枢纽机场", "country": "Q884"},
            {"qt": "universal", "kind": "all_target_class", "type": "航空公司", "rel": "枢纽机场", "klass": "国际机场"},
            {"qt": "universal", "kind": "all_target_class", "type": "航空公司", "rel": "枢纽机场", "klass": "国际机场", "country": "Q17"},
            {"qt": "universal", "kind": "all_target_class", "type": "航空公司", "rel": "枢纽机场", "klass": "国际机场", "country": "Q148"},
            {"qt": "universal", "kind": "all_have_rel", "type": "航空公司", "rel": "国家", "country": "Q884"},
            {"qt": "universal", "kind": "all_have_rel", "type": "航空公司", "rel": "运营机型", "country": "Q148"},
            {"qt": "universal", "kind": "all_have_rel", "type": "货运航空", "rel": "枢纽机场", "country": "Q148"},
            {"qt": "universal", "kind": "all_have_rel", "type": "机场", "rel": "国家", "country": "Q17"},
        ],
    }

    # ---- MERGE_ENTITY: 中华航空 absorbed into 华航集团
    others = [a for a in airlines if a not in ("中华航空", "华航集团")]
    C["MERGE_ENTITY"] = {
        "referral": pick_subjects(["中华航空"]),
        "count": [
            {"qt": "count", "kind": "members", "type": "航空公司"},
            {"qt": "count", "kind": "members", "type": "企业"},
            {"qt": "count", "kind": "with_rel", "type": "航空公司", "rel": "枢纽机场", "country": "Q865"},
            {"qt": "count", "kind": "with_rel", "type": "航空公司", "rel": "运营机型"},
            {"qt": "count", "kind": "with_rel", "type": "航空公司", "rel": "航空联盟"},
            {"qt": "count", "kind": "with_rel", "type": "航空公司", "rel": "子公司"},
            {"qt": "count", "kind": "with_rel", "type": "航空公司", "rel": "所有者"},
            {"qt": "count", "kind": "with_rel", "type": "航空公司", "rel": "国家"},
        ],
        "universal": [
            {"qt": "universal", "kind": "all_have_rel", "type": "航空公司", "rel": "国家", "country": "Q865"},
            {"qt": "universal", "kind": "all_is", "type": "航空公司", "klass": "企业", "country": "Q148"},
            {"qt": "universal", "kind": "all_have_rel", "type": "企业", "rel": "国家"},
            {"qt": "universal", "kind": "all_target_class", "subject": "华航集团", "rel": "子公司", "klass": "航空公司"},
            {"qt": "universal", "kind": "all_target_have_rel", "subject": "华航集团", "rel": "子公司", "rel2": "枢纽机场"},
            {"qt": "universal", "kind": "all_have_rel", "type": "航空公司", "rel": "运营机型", "country": "Q865"},
            {"qt": "universal", "kind": "all_have_rel", "type": "航空公司", "rel": "母组织"},
            {"qt": "universal", "kind": "all_target_have_rel", "type": "组织", "rel": "子公司", "rel2": "国家"},
        ],
    }

    # ---- SPLIT_CONCEPT: 机场 abolished, two daughters take over
    C["SPLIT_CONCEPT"] = {
        "referral": pick_subjects([]),
        "count": [
            {"qt": "count", "kind": "members", "type": "机场"},
            {"qt": "count", "kind": "members", "type": "机场", "country": "Q148"},
            {"qt": "count", "kind": "with_rel", "type": "机场", "rel": "服务城市"},
            {"qt": "count", "kind": "with_rel", "type": "机场", "rel": "国家"},
            {"qt": "count", "kind": "members", "type": "国际机场"},
            {"qt": "count", "kind": "members", "type": "普通机场"},
            {"qt": "count", "kind": "members", "type": "城市"},
            {"qt": "count", "kind": "members", "type": "国际机场", "country": "Q148"},
        ],
        "universal": [
            {"qt": "universal", "kind": "all_have_rel", "type": "机场", "rel": "服务城市"},
            {"qt": "universal", "kind": "all_have_rel", "type": "机场", "rel": "所在行政区"},
            {"qt": "universal", "kind": "all_have_rel", "type": "机场", "rel": "国家"},
            {"qt": "universal", "kind": "all_have_in_rel", "type": "机场", "rel": "枢纽机场"},
            {"qt": "universal", "kind": "all_is", "type": "机场", "klass": "国际机场"},
            {"qt": "universal", "kind": "all_have_rel", "type": "机场", "rel": "服务城市", "country": "Q148"},
            {"qt": "universal", "kind": "all_is", "type": "机场", "klass": "国际机场", "country": "Q17"},
            {"qt": "universal", "kind": "all_have_rel", "type": "机场", "rel": "所在行政区", "country": "Q884"},
            {"qt": "universal", "kind": "all_have_rel", "type": "机场", "rel": "服务城市", "country": "Q17"},
            {"qt": "universal", "kind": "all_is", "type": "机场", "klass": "国际机场", "country": "Q148"},
            {"qt": "universal", "kind": "all_have_in_rel", "type": "机场", "rel": "枢纽机场", "country": "Q148"},
            {"qt": "universal", "kind": "all_have_rel", "type": "机场", "rel": "所在行政区", "country": "Q17"},
        ],
    }
    return C


# ---------------------------------------------------------------- main
def jsonable(v):
    if isinstance(v, frozenset):
        return sorted(v)
    return v


def main():
    g1 = G(load(BASE / "data" / "graph_v1.json"))
    cands = build_candidates(g1)

    questions, labels, rows = [], [], []
    broken = []
    for op, qt_map in cands.items():
        g2 = G(load(GRAPHS[op]))
        for qt, cand in qt_map.items():
            scored = []
            for q in cand:
                a1, a2, exp = solve_pair(q, g1, g2)
                scored.append((q, a1, a2, exp))
            if op == "SPLIT_CONCEPT" and qt == "universal":
                # cell definition: universal over the abolished parent, false in v1
                scored = [s for s in scored if s[1] is False]
            picked = scored[:8]
            if len(picked) < 8:
                broken.append((op, qt, len(picked)))
            for n, (q, a1, a2, exp) in enumerate(picked, 1):
                qid = "%s-%s-%02d" % (op.lower(), qt, n)
                rec = {
                    "qid": qid, "operator": op, "qtype": qt,
                    "question": question_text(q), "query": q,
                    "answer_type": answer_type(q),
                    "gold_v1": jsonable(a1), "gold_v2": jsonable(a2),
                    "gold_v1_text": render(g1, a1), "gold_v2_text": render(g2, a2),
                    "expected": exp, "scope_size": g1.scope_size(q),
                }
                questions.append(rec)
                labels.append({"qid": qid, "operator": op, "qtype": qt,
                               "gold_v1": jsonable(a1), "gold_v2": jsonable(a2),
                               "expected": exp})
            n_flip = sum(1 for s in picked if s[3] == "flip")
            rows.append({"operator": op, "qtype": qt, "n": len(picked),
                         "stable": len(picked) - n_flip, "flip": n_flip,
                         "flip_rate": round(n_flip / len(picked), 3) if picked else None,
                         "prior": PRIOR[op][qt]})

    # no repeated surface form anywhere in the bank (T2.2 acceptance)
    seen, dups = {}, []
    for r in questions:
        if r["question"] in seen:
            dups.append((r["question"], seen[r["question"]], r["qid"]))
        seen[r["question"]] = r["qid"]
    if dups:
        raise SystemExit("duplicate questions: %r" % dups[:5])

    # ---- write
    qa_dir = BASE / "qa"
    qa_dir.mkdir(exist_ok=True)
    with open(qa_dir / "questions.jsonl", "w", encoding="utf-8") as f:
        for r in questions:
            f.write(json.dumps({k: r[k] for k in
                                ("qid", "operator", "qtype", "question", "query",
                                 "answer_type", "gold_v1", "gold_v1_text")},
                               ensure_ascii=False) + "\n")
    (BASE / "labels" / "labels.json").write_text(
        json.dumps(labels, ensure_ascii=False, indent=1), encoding="utf-8")

    with open(BASE / "labels" / "matrix.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["operator", "qtype", "n", "stable", "flip", "flip_rate", "prior", "prior_match"])
        for r in rows:
            if r["prior"] == "稳定":
                m = "match" if r["flip_rate"] == 0 else "DEVIATES"
            elif r["prior"] == "必翻":
                m = "match" if r["flip_rate"] == 1 else "DEVIATES"
            else:
                m = "consistent"
            w.writerow([r["operator"], r["qtype"], r["n"], r["stable"], r["flip"],
                        r["flip_rate"], r["prior"], m])

    summary = ["n_questions=%d" % len(questions), "broken_cells=%s" % broken, ""]
    for r in rows:
        summary.append("%-13s %-9s n=%d stable=%d flip=%d rate=%.3f prior=%s"
                       % (r["operator"], r["qtype"], r["n"], r["stable"], r["flip"],
                          r["flip_rate"], r["prior"]))
    summary.append("")
    for r in questions:
        summary.append("%s | %s | %s | v1=%s | v2=%s | %s"
                       % (r["qid"], r["question"], r["answer_type"],
                          r["gold_v1_text"], r["gold_v2_text"], r["expected"]))
    (BASE / "tools" / "gen_summary.txt").write_text("\n".join(summary), encoding="utf-8")
    print("questions", len(questions), "broken", broken)


if __name__ == "__main__":
    main()
