"""T1.1 raw data fetch: seed airlines -> one-hop whitelist neighbours.

Outputs data/raw_graph.json with nodes/edges plus fetch metadata.
No pruning here; pruning happens in build_graph.py.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qlever  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
os.makedirs(DATA, exist_ok=True)

SEED_COUNTRIES = {
    "Q148": "中国",
    "Q8646": "香港",
    "Q14773": "澳门",
    "Q865": "台湾地区",
    "Q17": "日本",
    "Q884": "韩国",
}
V = "VALUES ?ctry { " + " ".join("wd:" + q for q in SEED_COUNTRIES) + " }"
SEED_PAT = "?e wdt:P31/wdt:P279* wd:Q46970 ; wdt:P17 ?ctry ."


def batched(seq, n=120):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def vals(ids, var="?x"):
    return f"VALUES {var} {{ " + " ".join("wd:" + i for i in ids) + " }"


def fetch_labels(ids, store):
    for chunk in batched(sorted(ids)):
        rows = qlever.rows(f"""
            SELECT ?x ?l ?lang WHERE {{
              {vals(chunk)}
              ?x rdfs:label ?l . BIND(lang(?l) AS ?lang) FILTER(STRSTARTS(?lang, "zh"))
            }}""")
        for r in rows:
            e = qlever.qid(r["x"])
            store.setdefault(e, {"id": e, "labels": {}})["labels"][r["lang"]] = r["l"]


def class_membership(ids, classes):
    out = {}
    for cname, cqid in classes.items():
        found = set()
        for chunk in batched(sorted(ids)):
            rows = qlever.rows(f"""
                SELECT DISTINCT ?x WHERE {{
                  {vals(chunk)}
                  ?x wdt:P31/wdt:P279* {cqid} .
                }}""")
            found.update(qlever.qid(r["x"]) for r in rows)
        out[cname] = sorted(found)
    return out


def main():
    raw = {"meta": {}, "seeds": {}, "entities": {}, "edges": [], "class_membership": {}}
    edge_keys = set()

    def add_edge(h, rel, t, source):
        key = (h, rel, t)
        if key in edge_keys:
            return
        edge_keys.add(key)
        raw["edges"].append({"h": h, "rel": rel, "t": t, "source": source})

    print("[1/8] seed attributes")
    seed_rows = qlever.rows(f"""
        SELECT DISTINCT ?e ?ctry ?inception ?dissolved ?hq WHERE {{
          {SEED_PAT} {V}
          OPTIONAL {{ ?e wdt:P571 ?inception }}
          OPTIONAL {{ ?e wdt:P576 ?dissolved }}
          OPTIONAL {{ ?e wdt:P159 ?hq }}
        }}""")
    for r in seed_rows:
        e = qlever.qid(r["e"])
        raw["seeds"].setdefault(e, {
            "id": e,
            "country": qlever.qid(r["ctry"]),
            "inception": r.get("inception", "")[:4],
            "dissolved": r.get("dissolved", "")[:4],
            "hq": qlever.qid(r["hq"]) if "hq" in r else "",
            "labels": {},
        })
    print("   seeds:", len(raw["seeds"]))

    print("[2/8] seed labels + direct type")
    label_rows = qlever.rows(f"""
        SELECT ?e ?l ?lang WHERE {{
          {SEED_PAT} {V}
          ?e rdfs:label ?l . BIND(lang(?l) AS ?lang) FILTER(STRSTARTS(?lang, "zh"))
        }}""")
    for r in label_rows:
        e = qlever.qid(r["e"])
        raw["seeds"][e]["labels"][r["lang"]] = r["l"]

    p31_rows = qlever.rows(f"""
        SELECT DISTINCT ?e ?t WHERE {{ {SEED_PAT} {V} ?e wdt:P31 ?t }}""")
    for r in p31_rows:
        e = qlever.qid(r["e"])
        raw["seeds"][e].setdefault("p31", []).append(qlever.qid(r["t"]))

    print("[3/8] seed edges")
    rels = {"hub": "wdt:P113", "operated": "wdt:P121", "parent": "wdt:P749",
            "owner": "wdt:P127", "alliance": "wdt:P114", "subsidiary": "wdt:P355"}
    for name, prop in rels.items():
        rows = qlever.rows(f"""SELECT DISTINCT ?e ?o WHERE {{ {SEED_PAT} {V} ?e {prop} ?o }}""")
        for r in rows:
            add_edge(qlever.qid(r["e"]), name, qlever.qid(r["o"]), prop.split(":")[1])
        print(f"   {name}: {len(rows)}")

    for e, d in raw["seeds"].items():
        add_edge(e, "country", d["country"], "P17")
        if d.get("hq"):
            add_edge(e, "hq", d["hq"], "P159")

    print("[4/8] first-hop neighbour labels")
    endpoint_ids = sorted({e["t"] for e in raw["edges"]})
    fetch_labels(endpoint_ids, raw["entities"])
    print("   neighbours:", len(endpoint_ids))

    print("[5/8] class membership")
    classes = {
        "airport": "wd:Q1248784",
        "international_airport": "wd:Q644371",
        "aircraft_family": "wd:Q15056993",
        "aircraft_model": "wd:Q15056995",
        "aircraft_type": "wd:Q45296117",
        "airliner": "wd:Q210932",
        "jet_aircraft": "wd:Q206592",
        "regional_airliner": "wd:Q473625",
        "helicopter": "wd:Q34486",
        "city": "wd:Q515",
        "country": "wd:Q6256",
        "company": "wd:Q4830453",
        "organization": "wd:Q43229",
    }
    raw["class_membership"] = class_membership(endpoint_ids, classes)
    for k, v in raw["class_membership"].items():
        print(f"   {k}: {len(v)}")

    print("[6/8] structural edges for neighbours")
    aircraft_ids = sorted(set().union(*[
        set(raw["class_membership"][k]) for k in
        ["aircraft_family", "aircraft_model", "aircraft_type", "airliner",
         "jet_aircraft", "regional_airliner", "helicopter"]
    ]))
    for chunk in batched(aircraft_ids):
        rows = qlever.rows(f"""SELECT DISTINCT ?x ?o WHERE {{ {vals(chunk)} ?x wdt:P176 ?o }}""")
        for r in rows:
            add_edge(qlever.qid(r["x"]), "manufacturer", qlever.qid(r["o"]), "P176")

    airport_ids = raw["class_membership"]["airport"]
    for chunk in batched(airport_ids):
        for prop, name in [("wdt:P131", "located_in"), ("wdt:P931", "serves_place")]:
            rows = qlever.rows(f"""SELECT DISTINCT ?x ?o WHERE {{ {vals(chunk)} ?x {prop} ?o }}""")
            for r in rows:
                add_edge(qlever.qid(r["x"]), name, qlever.qid(r["o"]), prop.split(":")[1])

    city_ids = raw["class_membership"]["city"]
    for chunk in batched(city_ids):
        rows = qlever.rows(f"""SELECT DISTINCT ?x ?o WHERE {{ {vals(chunk)} ?x wdt:P131 ?o }}""")
        for r in rows:
            add_edge(qlever.qid(r["x"]), "located_in", qlever.qid(r["o"]), "P131")

    print("[7/8] second-hop labels/classes + country edges")
    new_endpoints = sorted({e["t"] for e in raw["edges"]} - set(raw["entities"]) - set(raw["seeds"]))
    fetch_labels(new_endpoints, raw["entities"])
    new_classes = class_membership(new_endpoints, {
        "city": "wd:Q515", "country": "wd:Q6256",
        "company": "wd:Q4830453", "organization": "wd:Q43229",
        "airport": "wd:Q1248784", "international_airport": "wd:Q644371",
    })
    for k, v in new_classes.items():
        merged = sorted(set(raw["class_membership"].get(k, [])) | set(v))
        raw["class_membership"][k] = merged
        print(f"   {k} (merged): {len(merged)}")

    country_targets = sorted(set().union(*[
        set(raw["class_membership"].get(k, [])) for k in ["airport", "city", "company", "organization"]
    ]))
    for chunk in batched(country_targets):
        rows = qlever.rows(f"""SELECT DISTINCT ?x ?o WHERE {{ {vals(chunk)} ?x wdt:P17 ?o }}""")
        for r in rows:
            add_edge(qlever.qid(r["x"]), "country", qlever.qid(r["o"]), "P17")

    manufacturer_ids = sorted({e["t"] for e in raw["edges"] if e["rel"] == "manufacturer"})
    for chunk in batched(manufacturer_ids):
        rows = qlever.rows(f"""SELECT DISTINCT ?x ?o WHERE {{ {vals(chunk)} ?x wdt:P17 ?o }}""")
        for r in rows:
            add_edge(qlever.qid(r["x"]), "country", qlever.qid(r["o"]), "P17")

    # admin-region chain: places referenced by located_in / serves_place get P131 + P17
    place_ids = sorted({e["t"] for e in raw["edges"] if e["rel"] in ("located_in", "serves_place")}
                       - set(country_targets))
    fetch_labels(place_ids, raw["entities"])
    for chunk in batched(place_ids):
        rows = qlever.rows(f"""SELECT DISTINCT ?x ?o WHERE {{ {vals(chunk)} ?x wdt:P131 ?o }}""")
        for r in rows:
            add_edge(qlever.qid(r["x"]), "located_in", qlever.qid(r["o"]), "P131")
        rows = qlever.rows(f"""SELECT DISTINCT ?x ?o WHERE {{ {vals(chunk)} ?x wdt:P17 ?o }}""")
        for r in rows:
            add_edge(qlever.qid(r["x"]), "country", qlever.qid(r["o"]), "P17")

    # alliance -> country
    alliance_ids = sorted({e["t"] for e in raw["edges"] if e["rel"] == "alliance"})
    for chunk in batched(alliance_ids):
        rows = qlever.rows(f"""SELECT DISTINCT ?x ?o WHERE {{ {vals(chunk)} ?x wdt:P17 ?o }}""")
        for r in rows:
            add_edge(qlever.qid(r["x"]), "country", qlever.qid(r["o"]), "P17")

    # country closure for place/organisation nodes (not aircraft: P17 there means origin)
    typed_non_aircraft = set().union(*[
        set(raw["class_membership"].get(k, [])) for k in ["airport", "city", "company", "organization"]
    ])
    have_country = {e["h"] for e in raw["edges"] if e["rel"] == "country"}
    need_country = sorted(typed_non_aircraft - have_country)
    for chunk in batched(need_country):
        rows = qlever.rows(f"""SELECT DISTINCT ?x ?o WHERE {{ {vals(chunk)} ?x wdt:P17 ?o }}""")
        for r in rows:
            add_edge(qlever.qid(r["x"]), "country", qlever.qid(r["o"]), "P17")

    # upward closure for subsidiaries: their parent/owner often already exists in the graph
    sub_ids = sorted({e["t"] for e in raw["edges"] if e["rel"] == "subsidiary"})
    for chunk in batched(sub_ids):
        for prop, name in [("wdt:P749", "parent"), ("wdt:P127", "owner")]:
            rows = qlever.rows(f"""SELECT DISTINCT ?x ?o WHERE {{ {vals(chunk)} ?x {prop} ?o }}""")
            for r in rows:
                add_edge(qlever.qid(r["x"]), name, qlever.qid(r["o"]), prop.split(":")[1])

    # broad country closure for any leftover non-aircraft, non-country endpoint
    aircraft_like = set().union(*[
        set(raw["class_membership"].get(k, [])) for k in
        ["aircraft_family", "aircraft_model", "aircraft_type", "airliner",
         "jet_aircraft", "regional_airliner", "helicopter"]
    ])
    all_endpoints = {e["t"] for e in raw["edges"]} | {e["h"] for e in raw["edges"]}
    have_country = {e["h"] for e in raw["edges"] if e["rel"] == "country"}
    need_country = sorted(all_endpoints - aircraft_like - set(raw["class_membership"]["country"]) - have_country)
    for chunk in batched(need_country):
        rows = qlever.rows(f"""SELECT DISTINCT ?x ?o WHERE {{ {vals(chunk)} ?x wdt:P17 ?o }}""")
        for r in rows:
            add_edge(qlever.qid(r["x"]), "country", qlever.qid(r["o"]), "P17")

    print("[8/8] final label pass")
    final_missing = sorted({e["t"] for e in raw["edges"]} - set(raw["entities"]) - set(raw["seeds"]))
    fetch_labels(final_missing, raw["entities"])
    print("   endpoints still unlabelled:", len(final_missing))

    raw["meta"] = {
        "endpoint": qlever.ENDPOINT,
        "seed_countries": SEED_COUNTRIES,
        "n_seeds": len(raw["seeds"]),
        "n_neighbour_entities": len(raw["entities"]),
        "n_edges_raw": len(raw["edges"]),
        "relation_whitelist": ["P113 hub", "P121 operated", "P749 parent", "P127 owner",
                               "P114 alliance", "P17 country", "P159 hq", "P176 manufacturer",
                               "P131 located_in", "P931 serves_place"],
    }
    with open(os.path.join(DATA, "raw_graph.json"), "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=1)
    print(json.dumps(raw["meta"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
