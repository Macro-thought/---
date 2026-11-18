# -*- coding: utf-8 -*-
"""T2.1 Chinese corpus: verbalise graph_v1 into 3-5 sentences per entity.

Design constraints from the task book:
* 3-5 sentences per entity, no empty document;
* >= 3 wording variants per entity type, chosen deterministically by entity id
  so the corpus is reproducible and not one flat template;
* no term leakage (no P-codes, no Q-ids, no "wikidata", no URLs);
* the corpus is generated from G_v1 only and never changes across variants,
  which is what makes "only the graph changes" a clean intervention.
"""
import json
import re
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

COUNTRY_SHORT = {"Q148": "中国", "Q17": "日本", "Q865": "台湾地区", "Q884": "韩国",
                 "Q8646": "香港", "Q334": "新加坡", "Q869": "泰国", "Q833": "马来西亚"}

SUBTYPE_WORD = {
    "航空公司": "航空公司", "货运航空": "货运航空公司", "支线航空": "支线航空公司",
    "低成本航空": "低成本航空公司", "直升机航空": "直升机航空公司",
}
CLASS_WORD = {"国际机场": "国际机场", "普通机场": "机场"}
KIND_WORD = {"固定翼机型": "固定翼飞机", "直升机": "直升机"}
TYPE_WORD = {"企业": "企业", "组织": "机构", "其他": "实体"}

# One known-bad Wikidata zh label (a duplicated character plus ASCII). The
# English name is unambiguous, so the corpus uses it.
LABEL_FIX = {"Q277491": "萨博340"}

LEAK = re.compile(r"(P\d{2,}|Q\d+|wikidata|Wikidata|http)", re.I)


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def join(items, limit=3):
    items = list(dict.fromkeys(items))
    if len(items) > limit:
        return "、".join(items[:limit]) + "等"
    return "、".join(items)


def variant(eid, n):
    return sum(ord(c) for c in eid) % n


def rotate(items, k):
    if not items:
        return []
    k %= len(items)
    return items[k:] + items[:k]


class Corpus:
    def __init__(self, g):
        self.g = g
        self.nodes = {n["id"]: n for n in g["entities"]}
        self.out = defaultdict(list)
        self.inn = defaultdict(list)
        for e in g["edges"]:
            self.out[e["h"]].append(e)
            self.inn[e["t"]].append(e)

    def lab(self, i):
        n = self.nodes.get(i)
        if not n:
            return None
        return LABEL_FIX.get(i) or n["label_zh"]

    def rel(self, i, r):
        vals = [self.lab(e["t"]) for e in self.out.get(i, []) if e["rel"] == r]
        return [v for v in vals if v]

    def inrel(self, i, r):
        vals = [self.lab(e["h"]) for e in self.inn.get(i, []) if e["rel"] == r]
        return [v for v in vals if v]

    def country(self, i):
        qid = self.nodes[i].get("props", {}).get("country")
        if not qid:
            return None
        return COUNTRY_SHORT.get(qid) or self.lab(qid)

    def en(self, i):
        en = self.nodes[i].get("label_en")
        return None if (not en or en == self.lab(i)) else en

    # ---------------- per type ----------------
    def airline(self, i):
        n = self.nodes[i]
        label = self.lab(i)
        sub = SUBTYPE_WORD.get(n.get("props", {}).get("p31_subtype"), "航空公司")
        c = self.country(i) or "某一国家"
        hubs = self.rel(i, "枢纽机场")
        ac = self.rel(i, "运营机型")
        hq = self.rel(i, "总部")
        year = n.get("props", {}).get("inception")
        parent = self.rel(i, "母组织")
        owner = self.rel(i, "所有者")
        subs = self.rel(i, "子公司")
        alliance = self.rel(i, "航空联盟")

        v = variant(i, 3)
        if v == 0:
            head = "%s是一家%s的%s。" % (label, c, sub)
        elif v == 1:
            en = self.en(i)
            head = "%s是一家%s的%s。" % (("%s（%s）" % (label, en)) if en else label, c, sub)
        else:
            head = "%s是%s的一家%s。" % (label, c, sub)

        # The hub sentence is the target of every referral question, so it is
        # never rotated out; the other facts rotate to keep the wording varied.
        hub_sent = ("它的枢纽机场包括%s。" % join(hubs)) if hubs else None
        facts = []
        if ac:
            facts.append("它运营的机型包括%s。" % join(ac))
        if hq:
            facts.append("公司总部设在%s。" % join(hq, 2))
        if year:
            facts.append("它成立于%s年。" % year)
        if parent:
            facts.append("它隶属于%s。" % join(parent, 2))
        if owner:
            facts.append("它的所有者包括%s。" % join(owner, 2))
        if subs:
            facts.append("旗下子公司包括%s。" % join(subs, 2))
        if alliance:
            facts.append("它是%s的成员。" % join(alliance, 2))

        sents = [head]
        if hub_sent:
            sents.append(hub_sent)
        sents += rotate(facts, v)[:5 - len(sents)]
        if len(sents) < 3:
            sents.append("它在%s运营。" % c)
        if len(sents) < 3:
            sents.append("在图谱分类中，它属于「航空公司」这一类。")
        return sents[:5]

    def airport(self, i):
        n = self.nodes[i]
        label = self.lab(i)
        cls = CLASS_WORD.get(n.get("props", {}).get("airport_class"), "机场")
        c = self.country(i) or "某一国家"
        cities = self.rel(i, "服务城市")
        admin = self.rel(i, "所在行政区")

        facts = []
        if cities:
            facts.append("它主要服务%s。" % join(cities, 2))
        if admin:
            facts.append("它位于%s。" % join(admin, 2))
        facts.append("它所在的国家是%s。" % c)

        v = variant(i, 3)
        cls_ok = cls not in label
        if v == 0:
            head = ("%s是一座%s。" % (label, cls)) if cls_ok else ("%s是%s的一座机场。" % (label, c))
        elif v == 1:
            en = self.en(i)
            base = "%s（%s）" % (label, en) if en else label
            head = ("%s是一座%s。" % (base, cls)) if cls_ok else ("%s是%s的一座机场。" % (base, c))
        else:
            head = "%s是%s的一座%s。" % (label, c, cls)

        sents = [head] + rotate(facts, v)[:3]
        if len(sents) < 3:
            sents.append("在图谱分类中，它属于「机场」这一类。")
        return sents[:4]

    def aircraft(self, i):
        n = self.nodes[i]
        label = self.lab(i)
        kind = KIND_WORD.get(n.get("props", {}).get("aircraft_class"), "飞机")
        maker = self.rel(i, "制造商")

        v = variant(i, 3)
        if v == 0:
            head = ("%s是由%s研制的%s。" % (label, join(maker, 2), kind)) if maker else ("%s是一种%s。" % (label, kind))
        elif v == 1:
            en = self.en(i)
            head = ("%s（%s）是%s的产品，属于%s。" % (label, en, join(maker, 2), kind)) if (en and maker) \
                else ("%s是一种%s。" % (label, kind))
        else:
            head = ("%s是%s研发的%s。" % (label, join(maker, 2), kind)) if maker else ("%s是一种%s。" % (label, kind))

        facts = []
        if maker:
            facts.append("它的制造商是%s。" % join(maker, 2))
        facts.append("在图谱分类中，它属于「机型」这一类。")
        sents = ([head] + facts)[:3]
        if len(sents) < 3:
            sents.append("它属于%s这一类。" % kind)
        return sents[:3]

    def city(self, i):
        label = self.lab(i)
        c = self.country(i) or "某一国家"
        admin = self.rel(i, "所在行政区")
        v = variant(i, 3)
        head = ["%s是%s的一座城市。" % (label, c),
                "%s位于%s，是一座城市。" % (label, c),
                "%s是%s的城市之一。" % (label, c)][v]
        facts = []
        if admin:
            facts.append("它位于%s。" % join(admin, 2))
        served_by = self.inrel(i, "服务城市")
        if served_by:
            facts.append("图中的%s等机场以它为服务城市。" % join(served_by, 2))
        if self.inrel(i, "总部"):
            facts.append("有航空公司把它作为总部所在地。")
        sents = [head] + rotate(facts, v)[:2]
        sents.append("在图谱分类中，它属于「城市」这一类。")
        if len(sents) < 3:
            sents.append("它所在的国家是%s。" % c)
        return sents[:4]

    def country_doc(self, i):
        label = self.lab(i)
        return ["%s是一个国家。" % label,
                "本图中的航空公司按国家归属于%s。" % label,
                "%s的机场与航线构成了图中的一部分。" % label]

    def generic(self, i, type_word):
        n = self.nodes[i]
        label = self.lab(i)
        c = self.country(i) or "某一国家"
        v = variant(i, 3)
        head = ["%s是%s的一家%s。" % (label, c, type_word),
                "%s是一家位于%s的%s。" % (label, c, type_word),
                "%s是%s的一个%s。" % (label, c, type_word)][v]
        facts = []
        for rel, tpl in (("母组织", "它隶属于%s。"), ("子公司", "旗下子公司包括%s。"),
                         ("所有者", "它的所有者包括%s。")):
            vals = self.rel(i, rel)
            if vals:
                facts.append(tpl % join(vals, 2))
        made = self.inrel(i, "制造商")
        if made:
            facts.append("它为%s等机型提供制造。" % join(made, 2))
        children = self.inrel(i, "母组织")
        if children:
            facts.append("%s等实体把它列为母公司。" % join(children, 2))
        facts.append("在图谱分类中，它属于「%s」这一类。" % n["type"])
        sents = [head] + rotate(facts, v)[:2]
        if len(sents) < 3:
            sents.append("它所在的国家是%s。" % c)
        return sents[:4]


def main():
    g = load(BASE / "data" / "graph_v1.json")
    c = Corpus(g)
    docs = []
    for n in g["entities"]:
        t = n["type"]
        if t == "航空公司":
            sents = c.airline(n["id"])
        elif t == "机场":
            sents = c.airport(n["id"])
        elif t == "机型":
            sents = c.aircraft(n["id"])
        elif t == "城市":
            sents = c.city(n["id"])
        elif t == "国家":
            sents = c.country_doc(n["id"])
        else:
            sents = c.generic(n["id"], TYPE_WORD.get(t, "实体"))
        sents = [s for s in dict.fromkeys(sents) if s]
        text = "".join(sents)
        docs.append({"doc_id": n["id"], "entity_id": n["id"], "text": text,
                     "n_sentences": len(sents)})

    # Tokens such as "Q300" inside the aircraft name 庞巴迪冲8Q300 are model
    # names, not leaked identifiers: anything occurring inside a real label is
    # allowed.
    label_tokens = set()
    for n in g["entities"]:
        for L in (n["label_zh"], n.get("label_en") or ""):
            label_tokens.update(LEAK.findall(L))
    leaks = []
    for d in docs:
        bad = [m for m in LEAK.findall(d["text"]) if m not in label_tokens]
        if bad:
            leaks.append((d["doc_id"], bad))

    short = [d["doc_id"] for d in docs if d["n_sentences"] < 3]
    out = BASE / "corpus" / "corpus.jsonl"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    stats = {
        "n_docs": len(docs),
        "n_sentences_dist": {k: sum(1 for d in docs if d["n_sentences"] == k) for k in (3, 4, 5)},
        "leaks": leaks[:10],
        "n_leaks": len(leaks),
        "docs_under_3_sentences": short,
        "avg_chars": round(sum(len(d["text"]) for d in docs) / len(docs), 1),
    }
    (BASE / "corpus" / "corpus_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
