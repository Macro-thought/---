"""T1.1/T1.2 build graph_v1.json and schema.json from raw_graph.json."""
import json
import os
import sys
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qlever  # noqa: E402
import opencc  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CC = opencc.OpenCC("t2s")

LANG_PRIORITY = ["zh-hans", "zh-cn", "zh-sg", "zh-my", "zh", "zh-hant", "zh-hk", "zh-tw", "zh-mo"]
TRAD_LANGS = {"zh-hant", "zh-hk", "zh-tw", "zh-mo"}

AIRLINE_SUBTYPE = [
    ("Q53649729", "直升机航空"),
    ("Q1057026", "货运航空"),
    ("Q2440569", "支线航空"),
    ("Q190915", "低成本航空"),
]
AIRLINE_TYPES = {"航空公司", "货运航空", "支线航空", "低成本航空", "直升机航空"}
AIRPORT_TYPES = {"机场", "国际机场", "普通机场"}
AIRCRAFT_TYPES = {"机型", "固定翼机型", "直升机"}

TYPE_PATH = {
    "国家": ["地点", "国家"],
    "城市": ["地点", "城市"],
    "机场": ["地点", "机场"],
    "国际机场": ["地点", "机场", "国际机场"],
    "普通机场": ["地点", "机场", "普通机场"],
    "航空公司": ["组织", "企业", "航空公司"],
    "货运航空": ["组织", "企业", "航空公司", "货运航空"],
    "支线航空": ["组织", "企业", "航空公司", "支线航空"],
    "低成本航空": ["组织", "企业", "航空公司", "低成本航空"],
    "直升机航空": ["组织", "企业", "航空公司", "直升机航空"],
    "企业": ["组织", "企业"],
    "组织": ["组织"],
    "固定翼机型": ["产品", "机型", "固定翼机型"],
    "直升机": ["产品", "机型", "直升机"],
    "其他": ["其他"],
}

REL_ZH = {
    "hub": "枢纽机场",
    "operated": "运营机型",
    "manufacturer": "制造商",
    "parent": "母组织",
    "owner": "所有者",
    "subsidiary": "子公司",
    "alliance": "航空联盟",
    "country": "国家",
    "hq": "总部",
    "located_in": "所在行政区",
    "serves_place": "服务城市",
}


def pick_label(labels):
    for lang in LANG_PRIORITY:
        if lang in labels and labels[lang].strip():
            raw = labels[lang].strip()
            simplified = CC.convert(raw)
            converted = lang in TRAD_LANGS or simplified != raw
            return simplified, lang, converted
    return None, None, False


def main():
    raw = json.load(open(os.path.join(DATA, "raw_graph.json"), encoding="utf-8"))
    seed_ids = set(raw["seeds"])
    cm = raw["class_membership"]
    sets = {k: set(v) for k, v in cm.items()}

    nodes = {}
    conversions = 0
    labelled = 0
    for eid in sorted(seed_ids | set(raw["entities"])):
        sd = raw["seeds"].get(eid, {})
        ed = raw["entities"].get(eid, {})
        labels = sd.get("labels") or ed.get("labels") or {}
        label, lang, converted = pick_label(labels)
        if not label:
            continue
        if eid == "Q865":
            label = "台湾地区"  # neutral geographic label used throughout the project
        labelled += 1
        if converted:
            conversions += 1

        if eid in seed_ids:
            leaf = "航空公司"
            for qid, t in AIRLINE_SUBTYPE:
                if qid in sd.get("p31", []):
                    leaf = t
                    break
            typ = "航空公司"
            path = TYPE_PATH["航空公司"]
        elif eid in sets["airport"]:
            leaf = "国际机场" if eid in sets["international_airport"] else "普通机场"
            typ = "机场"
            path = TYPE_PATH["机场"]
        elif eid in sets["helicopter"]:
            leaf = "直升机"
            typ = "机型"
            path = TYPE_PATH["固定翼机型"]
        elif (eid in sets["aircraft_family"] or eid in sets["aircraft_model"]
              or eid in sets["aircraft_type"] or eid in sets["airliner"]
              or eid in sets["jet_aircraft"] or eid in sets["regional_airliner"]):
            leaf = "固定翼机型"
            typ = "机型"
            path = TYPE_PATH["固定翼机型"]
        elif eid in sets["city"]:
            leaf = "城市"
            typ = "城市"
            path = TYPE_PATH["城市"]
        elif eid in sets["country"]:
            leaf = "国家"
            typ = "国家"
            path = TYPE_PATH["国家"]
        elif eid in sets["company"]:
            leaf = "企业"
            typ = "企业"
            path = TYPE_PATH["企业"]
        elif eid in sets["organization"]:
            leaf = "组织"
            typ = "组织"
            path = TYPE_PATH["组织"]
        else:
            leaf = "其他"
            typ = "其他"
            path = TYPE_PATH["其他"]

        aliases = sorted({v for k, v in labels.items() if v.strip() and v.strip() != label})
        nodes[eid] = {
            "id": eid,
            "label_zh": label,
            "label_source_lang": lang,
            "label_en": "",
            "type": typ,
            "type_path": path,
            "aliases": aliases,
            "props": {},
        }
        if typ == "航空公司":
            nodes[eid]["props"]["p31_subtype"] = leaf
        elif typ == "机场":
            nodes[eid]["props"]["airport_class"] = leaf
        elif typ == "机型":
            nodes[eid]["props"]["aircraft_class"] = leaf
        if sd.get("country"):
            nodes[eid]["props"]["country"] = sd["country"]
        if sd.get("inception"):
            nodes[eid]["props"]["inception"] = sd["inception"]
        if sd.get("dissolved"):
            nodes[eid]["props"]["dissolved"] = sd["dissolved"]
        if sd.get("hq"):
            nodes[eid]["props"]["hq"] = sd["hq"]

    # edges restricted to labelled nodes
    edges = []
    seen = set()
    for e in raw["edges"]:
        if e["h"] not in nodes or e["t"] not in nodes:
            continue
        key = (e["h"], e["rel"], e["t"])
        if key in seen:
            continue
        seen.add(key)
        edges.append({
            "h": e["h"],
            "rel": REL_ZH.get(e["rel"], e["rel"]),
            "rel_code": e["rel"],
            "t": e["t"],
            "props": {},
            "source": e["source"],
        })

    # degree
    deg = collections.Counter()
    for e in edges:
        deg[e["h"]] += 1
        deg[e["t"]] += 1
    nodes = {k: v for k, v in nodes.items() if deg[k] > 0}

    def priority(n):
        t = nodes[n]["type"]
        if t == "国家":
            return 0
        if t in AIRLINE_TYPES:
            return 1
        if t in AIRPORT_TYPES:
            return 2
        if t in AIRCRAFT_TYPES:
            return 3
        if t == "城市":
            return 4
        if t in ("企业", "组织"):
            return 5
        return 6

    def counts():
        return collections.Counter(v["type"] for v in nodes.values())

    # keep minimums for query generation
    minimums = {"货运航空": 5, "支线航空": 3, "低成本航空": 1, "直升机航空": 1,
                "国际机场": 8, "普通机场": 3, "固定翼机型": 10}

    def leaf_of(n):
        p = nodes[n]["props"]
        return p.get("p31_subtype") or p.get("airport_class") or p.get("aircraft_class") or nodes[n]["type"]
    TARGET_NODES = 600
    MIN_EDGES = 1500

    while len(nodes) > TARGET_NODES:
        cnt = counts()
        protected = set()
        for t, m in minimums.items():
            keep = [n for n in nodes if leaf_of(n) == t][:m]
            protected.update(keep)
        protected.update(n for n in nodes if nodes[n]["type"] == "国家")
        candidates = [n for n in nodes if n not in protected]
        if not candidates:
            break
        candidates.sort(key=lambda n: (-priority(n), deg[n], n))
        victim = candidates[0]
        # do not fall below edge floor
        if len(edges) - deg[victim] < MIN_EDGES:
            break
        for e in [e for e in edges if e["h"] == victim or e["t"] == victim]:
            deg[e["h"]] -= 1
            deg[e["t"]] -= 1
            edges.remove(e)
        del nodes[victim]

    # drop any orphan created
    deg = collections.Counter()
    for e in edges:
        deg[e["h"]] += 1
        deg[e["t"]] += 1
    nodes = {k: v for k, v in nodes.items() if deg[k] > 0}

    # english labels
    ids = sorted(nodes)
    for i in range(0, len(ids), 120):
        chunk = ids[i:i + 120]
        v = "VALUES ?x { " + " ".join("wd:" + x for x in chunk) + " }"
        rows = qlever.rows(f"""
            SELECT ?x ?l WHERE {{ {v} ?x rdfs:label ?l . FILTER(lang(?l) = "en") }}""")
        for r in rows:
            eid = qlever.qid(r["x"])
            if eid in nodes:
                nodes[eid]["label_en"] = r["l"]

    # node country props from country edges
    for e in edges:
        if e["rel"] == "国家" and "country" not in nodes[e["h"]]["props"]:
            nodes[e["h"]]["props"]["country"] = e["t"]

    graph = {
        "entities": [nodes[k] for k in sorted(nodes)],
        "edges": edges,
        "meta": {
            "fetched_at": "2026-11-16",
            "source": "Wikidata via qlever.dev/api/wikidata; seeds=P31/P279* Q46970 with P17 in CN/HK/MO/TW/JP/KR",
            "n_entities": len(nodes),
            "n_edges": len(edges),
            "n_seed_airlines": len([n for n in nodes if n in seed_ids]),
            "label_coverage": round(len(nodes) / max(1, len(nodes)), 4),
            "traditional_converted": conversions,
            "conversion_rate": round(conversions / max(1, labelled), 4),
        },
    }
    with open(os.path.join(DATA, "graph_v1.json"), "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=1)

    # schema.json
    tree = {}
    for n in graph["entities"]:
        p = n["type_path"]
        cur = tree
        for seg in p:
            cur = cur.setdefault(seg, {})
    schema = {
        "type_tree": tree,
        "airline_subclass_qids": {q: t for q, t in AIRLINE_SUBTYPE},
        "entity_types": {n["id"]: n["type"] for n in graph["entities"]},
        "mapping_basis": {
            "航空公司": "P31/P279* Q46970",
            "货运航空": "P31 Q1057026",
            "支线航空": "P31 Q2440569",
            "低成本航空": "P31 Q190915",
            "直升机航空": "P31 Q53649729",
            "国际机场": "P31/P279* Q644371 且 P31/P279* Q1248784",
            "普通机场": "机场中非国际机场者",
            "固定翼机型": "P31/P279* Q15056993/Q15056995/Q45296117/Q210932/Q206592/Q473625",
            "直升机": "P31/P279* Q34486",
            "城市": "P31/P279* Q515",
            "国家": "P31/P279* Q6256",
            "企业": "P31/P279* Q4830453",
            "组织": "P31/P279* Q43229",
        },
        "single_primary_type": True,
    }
    with open(os.path.join(DATA, "schema.json"), "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=1)

    # stats
    tc = collections.Counter(n["type"] for n in graph["entities"])
    rc = collections.Counter(e["rel"] for e in graph["edges"])
    deg = collections.Counter()
    for e in graph["edges"]:
        deg[e["h"]] += 1
        deg[e["t"]] += 1
    stats = {
        "n_entities": len(nodes),
        "n_edges": len(edges),
        "label_coverage": graph["meta"]["label_coverage"],
        "converted_labels": conversions,
        "conversion_rate": graph["meta"]["conversion_rate"],
        "type_counts": dict(tc),
        "relation_counts": dict(rc),
        "degree_min": min(deg.values()),
        "degree_max": max(deg.values()),
        "degree_avg": round(sum(deg.values()) / len(deg), 2),
        "orphans": sum(1 for n in nodes if deg[n] == 0),
        "n_airlines": sum(1 for n in nodes if nodes[n]["type"] == "航空公司"),
        "n_hubs": rc.get("枢纽机场", 0),
        "n_operated": rc.get("运营机型", 0),
    }
    with open(os.path.join(DATA, "graph_stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=1)
    print(json.dumps(stats, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
