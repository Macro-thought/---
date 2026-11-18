# -*- coding: utf-8 -*-
"""Dump structural summary of graph_v1 for solver design."""
import json
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
g = json.load(open(BASE / "data" / "graph_v1.json", encoding="utf-8"))
ents = {e["id"]: e for e in g["entities"]}
edges = g["edges"]

out = []
def p(*a):
    out.append(" ".join(str(x) for x in a))

p("=== TYPES ===")
p(Counter(e["type"] for e in g["entities"]).most_common())
p("=== TYPE_PATH ===")
for k, v in Counter(tuple(e["type_path"]) for e in g["entities"]).most_common():
    p(k, v)

p("=== PROPS KEYS by type ===")
d = defaultdict(Counter)
for e in g["entities"]:
    for k in e.get("props", {}):
        d[e["type"]][k] += 1
for t, c in d.items():
    p(t, dict(c))

p("=== p31_subtype ===")
p(Counter(e.get("props", {}).get("p31_subtype") for e in g["entities"]).most_common())
p("=== airport_class ===")
p(Counter(e.get("props", {}).get("airport_class") for e in g["entities"]).most_common())
p("=== aircraft_class ===")
p(Counter(e.get("props", {}).get("aircraft_class") for e in g["entities"]).most_common())

p("=== RELS ===")
relc = Counter(e["rel"] for e in edges)
for k, v in relc.most_common():
    p(k, v)

p("=== REL by source type -> target type (top 40) ===")
tri = Counter((ents.get(e["h"], {}).get("type"), e["rel"], ents.get(e["t"], {}).get("type")) for e in edges)
for k, v in tri.most_common(40):
    p(k, v)

p("=== SAMPLE per type ===")
seen = set()
for e in g["entities"]:
    if e["type"] in seen:
        continue
    seen.add(e["type"])
    p(json.dumps(e, ensure_ascii=False))

p("=== AIRLINE country via prop vs edge ===")
air = set(e["id"] for e in g["entities"] if e["type"] == "航空公司")
prop_c = Counter(ents[i].get("props", {}).get("country") for i in air)
p("prop country:", prop_c.most_common())
edge_c = Counter(e["t"] for e in edges if e["rel"] == "国家" and e["h"] in air)
p("edge country:", edge_c.most_common())
no_country = [i for i in air if "country" not in ents[i].get("props", {})]
p("airlines without prop country:", len(no_country), no_country[:10])

p("=== label samples with airport_class ===")
for e in g["entities"]:
    if e.get("props", {}).get("airport_class"):
        p(e["id"], e["label_zh"], e["type"], e["props"].get("airport_class"))

Path(BASE / "tools" / "shapes.txt").write_text("\n".join(out), encoding="utf-8")
print("ok", len(out))
