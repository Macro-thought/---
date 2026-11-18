"""T1.3 schema operators: REFINE_TYPE / RESTRICT_REL / MERGE_ENTITY / SPLIT_CONCEPT
plus the ADD_INST control. Every operator is deterministic and returns (graph2, diff).
"""
import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
GRAPHS = os.path.join(ROOT, "ops", "graphs")
os.makedirs(GRAPHS, exist_ok=True)


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def node_map(g):
    return {n["id"]: n for n in g["entities"]}


def is_a(node, type_name):
    return node["type"] == type_name or type_name in node.get("type_path", [])


def refine_type(g, params):
    g2 = copy.deepcopy(g)
    parent = params["parent"]
    attr = params["attribute"]
    modified = []
    for n in g2["entities"]:
        if n["type"] != parent:
            continue
        leaf = n.get("props", {}).get(attr)
        if leaf and leaf != parent and leaf not in n["type_path"]:
            before = n["type"]
            n["type"] = leaf
            n["type_path"] = n["type_path"] + [leaf]
            modified.append({"id": n["id"], "label": n["label_zh"], "from": before, "to": leaf})
    diff = {
        "op": "REFINE_TYPE",
        "params": params,
        "modified_nodes": modified,
        "n_modified": len(modified),
        "added_types": sorted({m["to"] for m in modified}),
        "n_edges_before": len(g["edges"]),
        "n_edges_after": len(g2["edges"]),
    }
    return g2, diff


def split_concept(g, params):
    """Concept split: the parent concept is abolished and replaced by two
    daughters. Unlike REFINE_TYPE (which keeps the parent so that membership is
    preserved), the parent is removed from type_path, so the parent class no
    longer denotes any instance. This is what makes a universal query over the
    parent turn vacuously true after the split.
    """
    g2 = copy.deepcopy(g)
    parent = params["parent"]
    attr = params["attribute"]
    modified = []
    for n in g2["entities"]:
        if n["type"] != parent:
            continue
        leaf = n.get("props", {}).get(attr)
        if leaf and leaf != parent:
            before = n["type"]
            n["type"] = leaf
            n["type_path"] = [t for t in n["type_path"] if t != parent] + [leaf]
            modified.append({"id": n["id"], "label": n["label_zh"], "from": before, "to": leaf})
    diff = {
        "op": "SPLIT_CONCEPT",
        "params": params,
        "modified_nodes": modified,
        "n_modified": len(modified),
        "added_types": sorted({m["to"] for m in modified}),
        "n_edges_before": len(g["edges"]),
        "n_edges_after": len(g2["edges"]),
    }
    return g2, diff


def restrict_rel(g, params):
    g2 = copy.deepcopy(g)
    nodes = node_map(g2)
    rel = params["rel"]
    attr = params["attribute"]
    value = params["value"]
    kept, removed = [], []
    for e in g2["edges"]:
        if e["rel"] != rel:
            kept.append(e)
            continue
        target = nodes.get(e["t"])
        if target and target.get("props", {}).get(attr) == value:
            kept.append(e)
        else:
            removed.append({"edge": e, "reason": f"target {e['t']} does not satisfy {attr}={value}"})
    g2["edges"] = kept
    diff = {
        "op": "RESTRICT_REL",
        "params": params,
        "removed_edges": removed,
        "n_removed": len(removed),
        "n_edges_before": len(g["edges"]),
        "n_edges_after": len(g2["edges"]),
    }
    return g2, diff


def merge_entity(g, params):
    g2 = copy.deepcopy(g)
    keep_id, merge_id = params["keep"], params["merge"]
    nodes = node_map(g2)
    if keep_id not in nodes or merge_id not in nodes:
        raise ValueError(f"merge endpoints missing: {keep_id}, {merge_id}")
    a, b = nodes[keep_id], nodes[merge_id]
    aliases = set(a.get("aliases", []))
    aliases.update(b.get("aliases", []))
    aliases.add(b["label_zh"])
    aliases.discard(a["label_zh"])
    a["aliases"] = sorted(aliases)
    # Type-classification facets describe the absorbed entity, not the keeper:
    # copying them would silently turn the group into an airline.
    for k, v in b.get("props", {}).items():
        if k in ("p31_subtype", "airport_class", "aircraft_class"):
            continue
        a.setdefault("props", {}).setdefault(k, v)

    rewired, deduped, self_loops = [], [], []
    new_edges, seen = [], set()
    for e in g2["edges"]:
        h = keep_id if e["h"] == merge_id else e["h"]
        t = keep_id if e["t"] == merge_id else e["t"]
        if e["h"] == merge_id or e["t"] == merge_id:
            rewired.append({"before": e, "after": {"h": h, "rel": e["rel"], "t": t}})
        if h == t:
            self_loops.append(e)
            continue
        key = (h, e["rel"], t)
        if key in seen:
            deduped.append(e)
            continue
        seen.add(key)
        new_edges.append({**e, "h": h, "t": t})
    g2["edges"] = new_edges
    g2["entities"] = [n for n in g2["entities"] if n["id"] != merge_id]
    diff = {
        "op": "MERGE_ENTITY",
        "params": params,
        "kept": {"id": keep_id, "label": a["label_zh"], "type": a["type"]},
        "absorbed": {"id": merge_id, "label": b["label_zh"], "type": b["type"]},
        "rewired_edges": len(rewired),
        "deduped_edges": len(deduped),
        "self_loops_dropped": len(self_loops),
        "n_entities_before": len(g["entities"]),
        "n_entities_after": len(g2["entities"]),
        "n_edges_before": len(g["edges"]),
        "n_edges_after": len(g2["edges"]),
    }
    return g2, diff


def add_inst(g, params):
    g2 = copy.deepcopy(g)
    pkg = params.get("package") or load(os.path.join(DATA, "add_instances.json"))
    have = {n["id"] for n in g2["entities"]}
    added_nodes = [copy.deepcopy(n) for n in pkg["entities"] if n["id"] not in have]
    added_edges = []
    keys = {(e["h"], e["rel"], e["t"]) for e in g2["edges"]}
    for e in pkg["edges"]:
        k = (e["h"], e["rel"], e["t"])
        if k in keys:
            continue
        keys.add(k)
        added_edges.append(copy.deepcopy(e))
    g2["entities"].extend(added_nodes)
    g2["edges"].extend(added_edges)
    diff = {
        "op": "ADD_INST",
        "params": {"package": "data/add_instances.json"},
        "added_nodes": added_nodes,
        "added_edges": added_edges,
        "n_added_nodes": len(added_nodes),
        "n_added_edges": len(added_edges),
        "n_edges_before": len(g["edges"]),
        "n_edges_after": len(g2["edges"]),
    }
    return g2, diff


OPS = {
    "REFINE_TYPE": refine_type,
    "RESTRICT_REL": restrict_rel,
    "MERGE_ENTITY": merge_entity,
    "SPLIT_CONCEPT": split_concept,
    "ADD_INST": add_inst,
}


def apply(g, params):
    return OPS[params["op"]](g, params)


DEFAULT_PARAMS = [
    {"op": "REFINE_TYPE", "parent": "航空公司", "attribute": "p31_subtype"},
    {"op": "RESTRICT_REL", "rel": "枢纽机场", "attribute": "airport_class", "value": "国际机场"},
    {"op": "MERGE_ENTITY", "keep": "Q5099568", "merge": "Q51756"},
    {"op": "SPLIT_CONCEPT", "parent": "机场", "attribute": "airport_class"},
    {"op": "ADD_INST"},
]


def main():
    g = load(os.path.join(DATA, "graph_v1.json"))
    manifest = []
    for params in DEFAULT_PARAMS:
        g2, diff = apply(g, params)
        name = params["op"]
        save(os.path.join(GRAPHS, name.lower() + ".json"), g2)
        save(os.path.join(GRAPHS, name.lower() + ".diff.json"), diff)
        manifest.append({
            "op": name,
            "params": params,
            "n_entities": len(g2["entities"]),
            "n_edges": len(g2["edges"]),
            "changed": {k: v for k, v in diff.items() if k.startswith("n_") or k == "added_types"},
        })
        print(name, "entities", len(g2["entities"]), "edges", len(g2["edges"]),
              "modified/added", {k: v for k, v in diff.items()
                                 if k in ("n_modified", "n_removed", "n_added_nodes", "n_added_edges", "rewired_edges")})
    save(os.path.join(GRAPHS, "manifest.json"), manifest)


if __name__ == "__main__":
    main()
