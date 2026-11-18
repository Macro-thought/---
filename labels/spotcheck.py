# -*- coding: utf-8 -*-
"""Manual spot-check of three gold labels, computed with plain loops over the
raw JSON (no solver functions), so an error in the solver would show up here.
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def airline_count(g):
    return sum(1 for n in g["entities"]
               if n["type"] == "航空公司" or "航空公司" in n.get("type_path", [])
               or n.get("props", {}).get("p31_subtype") == "航空公司")

def airports(g):
    """Resolve the CLASS NAME 机场 only (type / type_path), not the facet."""
    return [n for n in g["entities"]
            if n["type"] == "机场" or "机场" in n.get("type_path", [])]

out = []
def p(s):
    out.append(s)

g1 = load(BASE / "data" / "graph_v1.json")
gm = load(BASE / "ops" / "graphs" / "merge_entity.json")
gs = load(BASE / "ops" / "graphs" / "split_concept.json")
gr = load(BASE / "ops" / "graphs" / "restrict_rel.json")

# Q1 merge_entity-count-01
p("Q1 merge_entity-count-01 全图共有多少个航空公司？ gold 185 -> 184")
p("  v1 direct count = %d" % airline_count(g1))
p("  v2 direct count = %d" % airline_count(gm))
p("  Q51756 present v1/v2: %s / %s" % (
    any(n["id"] == "Q51756" for n in g1["entities"]),
    any(n["id"] == "Q51756" for n in gm["entities"])))
keep = [n for n in gm["entities"] if n["id"] == "Q5099568"][0]
p("  keeper Q5099568 type=%s props=%s" % (keep["type"], keep["props"]))

# Q2 split_concept-universal-01
p("")
p("Q2 split_concept-universal-01 是否所有机场都有服务城市？ gold 否 -> 是")
a1 = airports(g1)
served = {e["h"] for e in g1["edges"] if e["rel"] == "服务城市"}
p("  v1 airports=%d, with 服务城市=%d, all=%s"
  % (len(a1), sum(1 for n in a1 if n["id"] in served),
     len(a1) == sum(1 for n in a1 if n["id"] in served)))
a2 = airports(gs)
facets2 = [n for n in gs["entities"]
           if n.get("props", {}).get("airport_class") in ("国际机场", "普通机场")]
p("  v2 class-name 机场 resolved=%d (daughters still present by facet: %d)"
  % (len(a2), len(facets2)))
p("  => empty scope, universal vacuously TRUE=%s" % (len(a2) == 0))

# Q3 restrict_rel-referral-01
p("")
p("Q3 restrict_rel-referral-01 「朱鹭航空」的枢纽机场是哪个（些）？ gold 新潟机场 -> 空")
name = "朱鹭航空"
sub1 = [n["id"] for n in g1["entities"]
        if n["label_zh"] == name or name in n.get("aliases", [])]
sub2 = [n["id"] for n in gr["entities"]
        if n["label_zh"] == name or name in n.get("aliases", [])]
t1 = [e["t"] for e in g1["edges"] if e["h"] in sub1 and e["rel"] == "枢纽机场"]
t2 = [e["t"] for e in gr["edges"] if e["h"] in sub2 and e["rel"] == "枢纽机场"]
lab = {n["id"]: n["label_zh"] for n in g1["entities"]}
cls = {n["id"]: n.get("props", {}).get("airport_class") for n in g1["entities"]}
p("  subject ids v1/v2: %s / %s" % (sub1, sub2))
p("  v1 hubs = %s (%s)" % ([lab[t] for t in t1], [cls[t] for t in t1]))
p("  v2 hubs = %s" % [lab[t] for t in t2])

(BASE / "logs").mkdir(exist_ok=True)
(BASE / "logs" / "spotcheck_t14.txt").write_text("\n".join(out), encoding="utf-8")
print("written")
