"""Build a small ADD_INST control package from Wikidata (SG/TH/MY flag carriers)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qlever  # noqa: E402
import opencc  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CC = opencc.OpenCC("t2s")
AIRLINES = [("Q32245", "新加坡航空", "Q334"), ("Q188710", "泰国国际航空", "Q869"),
            ("Q308952", "马来西亚航空", "Q833")]
COUNTRIES = {"Q334": "新加坡", "Q869": "泰国", "Q833": "马来西亚"}


def zh_labels(ids):
    out = {}
    v = "VALUES ?x { " + " ".join("wd:" + i for i in ids) + " }"
    rows = qlever.rows(f"""
        SELECT ?x ?l ?lang WHERE {{ {v} ?x rdfs:label ?l .
        BIND(lang(?l) AS ?lang) FILTER(STRSTARTS(?lang,"zh")) }}""")
    for r in rows:
        out.setdefault(qlever.qid(r["x"]), {})[r["lang"]] = r["l"]
    return out


def best(labels):
    for lang in ["zh-hans", "zh-cn", "zh", "zh-hant", "zh-tw", "zh-hk"]:
        if lang in labels:
            return CC.convert(labels[lang])
    return None


def main():
    hubs = {}
    hub_country = {}
    for aid, _, _ in AIRLINES:
        rows = qlever.rows(f"""
            SELECT DISTINCT ?o ?c WHERE {{ wd:{aid} wdt:P113 ?o . OPTIONAL {{ ?o wdt:P17 ?c }} }}""")
        for r in rows:
            o = qlever.qid(r["o"])
            hubs.setdefault(aid, []).append(o)
            if "c" in r:
                hub_country[o] = qlever.qid(r["c"])

    all_ids = [a for a, _, _ in AIRLINES] + [h for v in hubs.values() for h in v]
    labels = zh_labels(all_ids)

    entities, edges = [], []
    for aid, fallback, ctry in AIRLINES:
        label = best(labels.get(aid, {})) or fallback
        entities.append({
            "id": aid, "label_zh": label, "label_en": "", "type": "航空公司",
            "type_path": ["组织", "企业", "航空公司"], "aliases": [],
            "props": {"country": ctry, "p31_subtype": "航空公司"},
        })
        edges.append({"h": aid, "rel": "国家", "rel_code": "country", "t": ctry,
                      "props": {}, "source": "P17"})
        used = 0
        for h in hubs.get(aid, []):
            hl = best(labels.get(h, {}))
            if not hl:
                continue
            hc = hub_country.get(h, ctry)
            entities.append({
                "id": h, "label_zh": hl, "label_en": "", "type": "机场",
                "type_path": ["地点", "机场"], "aliases": [],
                "props": {"country": hc, "airport_class": "国际机场"},
            })
            edges.append({"h": aid, "rel": "枢纽机场", "rel_code": "hub", "t": h,
                          "props": {}, "source": "P113"})
            edges.append({"h": h, "rel": "国家", "rel_code": "country", "t": hc,
                          "props": {}, "source": "P17"})
            used += 1
        print(aid, label, "hubs:", used)

    for cid, clabel in COUNTRIES.items():
        entities.append({
            "id": cid, "label_zh": clabel, "label_en": "", "type": "国家",
            "type_path": ["地点", "国家"], "aliases": [], "props": {},
        })

    # dedupe entities and edges
    seen = set()
    uniq = []
    for e in entities:
        if e["id"] not in seen:
            seen.add(e["id"])
            uniq.append(e)
    ekeys = set()
    uedges = []
    for e in edges:
        k = (e["h"], e["rel"], e["t"])
        if k not in ekeys:
            ekeys.add(k)
            uedges.append(e)

    out = {"entities": uniq, "edges": uedges}
    with open(os.path.join(ROOT, "data", "add_instances.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("entities", len(uniq), "edges", len(uedges))


if __name__ == "__main__":
    main()
