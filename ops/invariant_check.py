# -*- coding: utf-8 -*-
"""T1.3 invariant self-check for graph_v1 and all five variants."""
import json
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
GRAPHS = BASE / "ops" / "graphs"

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def check(g, name):
    ids = {n["id"] for n in g["entities"]}
    dangling = [e for e in g["edges"] if e["h"] not in ids or e["t"] not in ids]
    deg = Counter()
    for e in g["edges"]:
        deg[e["h"]] += 1
        deg[e["t"]] += 1
    orphans = [n["id"] for n in g["entities"] if deg[n["id"]] == 0]
    no_type = [n["id"] for n in g["entities"] if not n.get("type") or not n.get("type_path")]
    no_label = [n["id"] for n in g["entities"] if not n.get("label_zh")]
    dup_nodes = [k for k, v in Counter(n["id"] for n in g["entities"]).items() if v > 1]
    dup_edges = [k for k, v in Counter((e["h"], e["rel"], e["t"]) for e in g["edges"]).items() if v > 1]
    no_source = [e for e in g["edges"] if not e.get("source")]
    n_parent_left = {
        "机场": sum(1 for n in g["entities"] if "机场" in n["type_path"]),
    }
    return {
        "graph": name,
        "n_entities": len(g["entities"]),
        "n_edges": len(g["edges"]),
        "dangling_edges": len(dangling),
        "orphans": len(orphans),
        "orphan_sample": orphans[:5],
        "nodes_without_type": len(no_type),
        "nodes_without_label": len(no_label),
        "duplicate_nodes": len(dup_nodes),
        "duplicate_edges": len(dup_edges),
        "edges_without_source": len(no_source),
        "members_of_机场": n_parent_left["机场"],
        "type_dist": dict(Counter(n["type"] for n in g["entities"]).most_common()),
        "ok": not (dangling or orphans or no_type or no_label or dup_nodes or dup_edges or no_source),
    }

if __name__ == "__main__":
    files = [("graph_v1", BASE / "data" / "graph_v1.json")]
    for op in ["refine_type", "restrict_rel", "merge_entity", "split_concept", "add_inst"]:
        files.append((op, GRAPHS / (op + ".json")))
    report = [check(load(p), n) for n, p in files]
    out = BASE / "ops" / "invariant_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in report:
        print(r["graph"], r["n_entities"], r["n_edges"], "ok=", r["ok"],
              "dangling", r["dangling_edges"], "orphans", r["orphans"],
              "dupE", r["duplicate_edges"], "机场members", r["members_of_机场"])
