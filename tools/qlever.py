"""Minimal QLever SPARQL client with retry/backoff and on-disk cache."""
import urllib.request
import urllib.parse
import urllib.error
import json
import time
import hashlib
import os

ENDPOINT = "https://qlever.dev/api/wikidata"
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")
os.makedirs(CACHE_DIR, exist_ok=True)

PREFIXES = """PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX p: <http://www.wikidata.org/prop/>
PREFIX ps: <http://www.wikidata.org/prop/statement/>
PREFIX pq: <http://www.wikidata.org/prop/qualifier/>
"""


def _cache_path(query):
    h = hashlib.sha1(query.encode("utf-8")).hexdigest()[:16]
    return os.path.join(CACHE_DIR, h + ".json")


def query(q, use_cache=True, retries=5, min_interval=1.5):
    full = q if q.lstrip().startswith("PREFIX") else PREFIXES + q
    path = _cache_path(full)
    if use_cache and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    url = ENDPOINT + "?" + urllib.parse.urlencode({"query": full})
    delay = min_interval
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/sparql-results+json",
                    "User-Agent": "schema-change-research/1.0 (academic; contact: local)",
                },
            )
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.loads(r.read().decode("utf-8"))
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            time.sleep(min_interval)
            return data
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(delay)
                delay *= 2
                continue
            raise
        except Exception as e:  # transient network
            last = e
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"QLever query failed after {retries} attempts: {last}")


def rows(q, **kw):
    data = query(q, **kw)
    out = []
    for b in data["results"]["bindings"]:
        out.append({k: v["value"] for k, v in b.items()})
    return out


def qid(uri):
    return uri.rsplit("/", 1)[-1]
