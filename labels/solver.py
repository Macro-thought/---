# -*- coding: utf-8 -*-
"""T1.4 deterministic solver.

No LLM, no heuristics that depend on surface wording: every answer is a set /
integer / boolean computed by walking the graph. The same question evaluated on
G_v1 and G_v2 yields the gold answers; their difference IS the expected label
("flip" vs "stable"). This is what keeps the gold labels from colluding with
the systems under test.

Class membership
----------------
`members(G, T)` is ancestor-inclusive and also accepts leaf facets, because the
v1 graph records the leaf classification as node props:

    T == node.type
    or T in node.type_path
    or T == props.p31_subtype / props.airport_class / props.aircraft_class

Consequences (these are the design decisions the paper must state):
* REFINE_TYPE keeps the parent in type_path, so membership is preserved and all
  REFINE questions are stable by construction.
* SPLIT_CONCEPT abolishes the parent (it is removed from type_path), so
  `members(G, parent)` becomes empty. A universal over the parent then becomes
  vacuously true -- the classic empty-domain failure mode.
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
FACETS = ("p31_subtype", "airport_class", "aircraft_class")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class G:
    def __init__(self, graph):
        self.graph = graph
        self.nodes = {n["id"]: n for n in graph["entities"]}
        self.out = {}
        for e in graph["edges"]:
            self.out.setdefault(e["h"], []).append(e)
        self.inn = {}
        for e in graph["edges"]:
            self.inn.setdefault(e["t"], []).append(e)

    # ---------- primitives ----------
    def is_member(self, i, T):
        n = self.nodes.get(i)
        if not n:
            return False
        if n.get("type") == T or T in n.get("type_path", []):
            return True
        props = n.get("props", {})
        return any(props.get(k) == T for k in FACETS)

    def members(self, T):
        return {n["id"] for n in self.graph["entities"] if self.is_member(n["id"], T)}

    def resolve(self, name):
        """Name -> set of ids. Label or alias, exact match (referral by name)."""
        out = set()
        for n in self.graph["entities"]:
            if n.get("label_zh") == name or name in n.get("aliases", []):
                out.add(n["id"])
        return out

    def targets(self, ids, rel):
        out = set()
        for i in ids:
            for e in self.out.get(i, []):
                if e["rel"] == rel:
                    out.add(e["t"])
        return out

    def sources(self, ids, rel):
        out = set()
        for i in ids:
            for e in self.inn.get(i, []):
                if e["rel"] == rel:
                    out.add(e["h"])
        return out

    def label(self, i):
        n = self.nodes.get(i)
        return n["label_zh"] if n else "(缺失节点 %s)" % i

    def country(self, i):
        return self.nodes.get(i, {}).get("props", {}).get("country")

    def scope(self, T, country=None):
        ids = self.members(T)
        if country:
            ids = {i for i in ids if self.country(i) == country}
        return ids

    def uset(self, q):
        """Scope of a universal: a named subject (alias-resolved) or a class."""
        if q.get("subject"):
            ids = self.resolve(q["subject"])
        else:
            ids = self.members(q["type"])
        if q.get("country"):
            ids = {i for i in ids if self.country(i) == q["country"]}
        return ids

    def klass_of(self, i):
        props = self.nodes.get(i, {}).get("props", {})
        return {props.get(k) for k in FACETS if props.get(k)}

    # ---------- query types ----------
    def solve(self, q):
        qt = q["qt"]
        if qt == "referral":
            subj = self.resolve(q["subject"])
            return frozenset(self.targets(subj, q["rel"]))
        if qt == "count":
            return self._count(q)
        if qt == "universal":
            return self._universal(q)
        raise ValueError("unknown qt: " + qt)

    def _count(self, q):
        kind = q["kind"]
        if kind == "members":
            return len(self.scope(q["type"], q.get("country")))
        if kind == "with_rel":
            ids = self.scope(q["type"], q.get("country"))
            return sum(1 for i in ids if self.targets({i}, q["rel"]))
        if kind == "rel_to":
            ids = self.scope(q["type"], q.get("country"))
            tgt = self.resolve(q["target"])
            return sum(1 for i in ids if self.targets({i}, q["rel"]) & tgt)
        raise ValueError("unknown count kind: " + kind)

    def _universal(self, q):
        """Universal statements. An empty scope is vacuously TRUE -- that is the
        behaviour that makes SPLIT_CONCEPT flip the universal cell."""
        kind = q["kind"]
        ids = self.uset(q)
        if kind == "all_have_rel":
            return all(bool(self.targets({i}, q["rel"])) for i in ids)
        if kind == "all_have_in_rel":
            return all(bool(self.sources({i}, q["rel"])) for i in ids)
        if kind == "all_target_class":
            for i in ids:
                for t in self.targets({i}, q["rel"]):
                    if not self.is_member(t, q["klass"]):
                        return False
            return True
        if kind == "all_is":
            return all(self.is_member(i, q["klass"]) for i in ids)
        if kind == "all_rel_to":
            tgt = self.resolve(q["target"])
            return all(bool(self.targets({i}, q["rel"]) & tgt) for i in ids)
        if kind == "all_target_have_rel":
            for i in ids:
                for t in self.targets({i}, q["rel"]):
                    if not self.targets({t}, q["rel2"]):
                        return False
            return True
        raise ValueError("unknown universal kind: " + kind)

    def scope_size(self, q):
        if q["qt"] == "universal":
            return len(self.uset(q))
        if q["qt"] == "count":
            return len(self.scope(q["type"], q.get("country")))
        return len(self.resolve(q["subject"]))


def render(cls, ans):
    """Human-readable gold answer."""
    if isinstance(ans, frozenset):
        return "、".join(sorted(cls.label(i) for i in ans)) if ans else "(空集)"
    if isinstance(ans, bool):
        return "是" if ans else "否"
    return str(ans)


def solve_pair(q, g1, g2):
    a1 = g1.solve(q)
    a2 = g2.solve(q)
    return a1, a2, ("flip" if a1 != a2 else "stable")


if __name__ == "__main__":
    g1 = G(load(BASE / "data" / "graph_v1.json"))
    g2 = G(load(BASE / "ops" / "graphs" / "split_concept.json"))
    q = {"qt": "universal", "kind": "all_have_rel", "type": "机场", "rel": "服务城市"}
    print("split universal:", g1.solve(q), g2.solve(q))
    q2 = {"qt": "count", "kind": "members", "type": "机场"}
    print("split count:", g1.solve(q2), g2.solve(q2))
