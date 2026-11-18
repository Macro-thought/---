# -*- coding: utf-8 -*-
"""Shared pieces for the three baselines.

There is no LLM key on this machine, so `read_answer` is an *extractive
placeholder*: it reads the relation word from the question and copies entity
names that follow it in the retrieved context. It is deliberately weak and is
only used to prove the pipeline is wired end to end. Pass `--llm qwen` to a
baseline to route the same context through a real model instead; nothing else
in the harness changes.
"""
import json
import math
import re
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CORPUS = BASE / "corpus" / "corpus.jsonl"
REL_WORDS = ["枢纽机场", "运营机型", "总部", "母公司", "子公司", "所有者", "航空联盟", "国家"]
FILLER = ("在图谱分类中", "本图中的")


def load_corpus():
    docs = []
    for line in open(CORPUS, encoding="utf-8"):
        docs.append(json.loads(line))
    return docs


def bigrams(s):
    s = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", s)
    return [s[i:i + 2] for i in range(len(s) - 1)] or [s]


class Index:
    """Minimal char-bigram TF-IDF. Pure stdlib so it runs anywhere."""

    def __init__(self, docs):
        self.docs = docs
        self.df = {}
        for d in docs:
            for t in set(bigrams(d["text"])):
                self.df[t] = self.df.get(t, 0) + 1
        self.n = len(docs)
        self.vecs = []
        for d in docs:
            tf = {}
            for t in bigrams(d["text"]):
                tf[t] = tf.get(t, 0) + 1
            v = {t: (1 + math.log(c)) * math.log((self.n + 1) / (self.df.get(t, 0) + 0.5))
                 for t, c in tf.items()}
            norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
            self.vecs.append({t: x / norm for t, x in v.items()})

    def search(self, query, k=5):
        tf = {}
        for t in bigrams(query):
            tf[t] = tf.get(t, 0) + 1
        qv = {t: (1 + math.log(c)) * math.log((self.n + 1) / (self.df.get(t, 0) + 0.5))
              for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in qv.values())) or 1.0
        scored = []
        for i, v in enumerate(self.vecs):
            s = sum(x * v.get(t, 0.0) for t, x in qv.items()) / norm
            if s > 0:
                scored.append((s, i))
        scored.sort(reverse=True)
        return [(round(s, 4), self.docs[i]) for s, i in scored[:k]]


def sentences(text):
    return [s for s in re.split(r"(?<=。)", text) if s.strip()]


def relation_in(question):
    for r in REL_WORDS:
        if r in question:
            return r
    return None


def names_in(text, names):
    """Longest-match, non-overlapping entity names present in text."""
    found = []
    for name in sorted(names, key=len, reverse=True):
        if name and name in text:
            start = text.find(name)
            if not any(s <= start < e for s, e, _ in found):
                found.append((start, start + len(name), name))
        if len(found) > 40:
            break
    return [n for _, _, n in sorted(found)]


def question_subject(question, names):
    for n in sorted(names, key=len, reverse=True):
        if "「%s」" % n in question:
            return n
    return None


def read_answer(question, context, names, triple_mode=False):
    """Extractive placeholder reader. Returns a string, never empty.

    triple_mode: the context is a list of "头实体的关系是尾实体。" triples, so a
    referral answer can be restricted to sentences whose head is the entity the
    question asks about. Text-chunk context (B1) does not have that structure and
    keeps the looser sentence scan.
    """
    if "多少个" in question:
        # cannot aggregate over the whole graph from top-k context; count what is
        # visible and say so is left to the caller's bookkeeping
        rel = relation_in(question)
        hits = set()
        for sent in sentences(context):
            if rel and rel in sent:
                hits.update(names_in(sent, names))
        return str(len(hits))
    if question.startswith("是否"):
        return "否" if ("并非" in context or "没有" in context) else "是"
    rel = relation_in(question)
    subject = question_subject(question, names)
    prefix = "%s的%s是" % (subject, rel) if (subject and rel) else None
    out = []
    for sent in sentences(context):
        if rel and rel not in sent:
            continue
        if triple_mode and prefix and not sent.startswith(prefix):
            continue
        tail = re.split(r"(?:包括|是)", sent, maxsplit=1)
        chunk = tail[1] if len(tail) > 1 else sent
        for n in names_in(chunk, names):
            if n != subject:
                out.append(n)
    return "、".join(dict.fromkeys(out))


def estimate_tokens(text):
    return max(1, int(len(text) / 1.5))


def run(questions, answer_fn, out_path, tag, extra=None):
    """answer_fn(q) -> (answer_text, context_text). Records per-question latency
    and an estimated token count (question + context + answer)."""
    rows = []
    t0 = time.time()
    for q in questions:
        t1 = time.perf_counter()
        ans, ctx = answer_fn(q)
        lat = (time.perf_counter() - t1) * 1000.0
        tin = estimate_tokens(q["question"]) + estimate_tokens(ctx)
        tout = estimate_tokens(ans)
        rows.append({"qid": q["qid"], "operator": q["operator"], "qtype": q["qtype"],
                     "system": tag, "answer": ans,
                     "latency_ms": round(lat, 2),
                     "context_chars": len(ctx),
                     "input_tokens_est": tin,
                     "output_tokens_est": tout,
                     "tokens_est": tin + tout})
    dt = time.time() - t0
    lat = sorted(r["latency_ms"] for r in rows)
    nonempty = sum(1 for r in rows if r["answer"].strip())
    summary = {
        "system": tag,
        "n": len(rows),
        "elapsed_s": round(dt, 2),
        "nonempty": nonempty,
        "nonempty_rate": round(nonempty / max(1, len(rows)), 4),
        "latency_ms_p50": lat[len(lat) // 2] if lat else 0,
        "latency_ms_p95": lat[int(len(lat) * 0.95) - 1] if lat else 0,
        "input_tokens_est_total": sum(r["input_tokens_est"] for r in rows),
        "output_tokens_est_total": sum(r["output_tokens_est"] for r in rows),
        "tokens_est_total": sum(r["tokens_est"] for r in rows),
        "answers": rows,
        "meta": extra or {},
    }
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return rows, dt
