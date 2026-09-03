"""common.py - shared loader and helpers for the DataRepublicans analysis scripts.

Every topic script (sources.py, money.py, ...) imports this module and nothing
else outside the Python standard library.  Run any topic script directly from
this folder; its outputs land in analysis/<topic>/.

Data files:
  datarep_nodes.csv      512 nodes (people, orgs, projects, concepts)
  datarep_edges.csv      1,059 relations with slice, confidence, source_url
  datarep_positions.csv  JSON (despite the extension): x/y layout per node
"""
import csv
import json
import os
from collections import defaultdict, deque
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
NODES_CSV = os.path.join(HERE, "datarep_nodes.csv")
EDGES_CSV = os.path.join(HERE, "datarep_edges.csv")
POSITIONS_JSON = os.path.join(HERE, "datarep_positions.csv")
OUT_DIR = os.path.join(HERE, "analysis")

TRUE_WORDS = {"yes", "true", "y", "1"}
FALSE_WORDS = {"no", "false", "n", "0"}


def split_multi(value):
    """Split a '|'-delimited cell into a clean list."""
    if not value:
        return []
    return [p.strip() for p in value.split("|") if p.strip()]


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_bool(value):
    v = (value or "").strip().lower()
    if v in TRUE_WORDS:
        return True
    if v in FALSE_WORDS:
        return False
    return None


def load():
    """Return (nodes, edges, positions).

    nodes: dict id -> row.  Added keys: slices (list), source_urls (list),
           magnitude (float|None), n_slices (int), primary_slice (str).
    edges: list of rows in file order.  Added keys: idx (0-based row number),
           slices (list), source_urls (list), directed (bool|None),
           directed_raw (original text).
    positions: dict id -> {"x": .., "y": ..}
    """
    nodes = {}
    with open(NODES_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            row["slices"] = split_multi(row.get("slices"))
            row["source_urls"] = split_multi(row.get("source_url"))
            row["magnitude"] = to_float(row.get("magnitude"))
            ns = (row.get("n_slices") or "").strip()
            row["n_slices"] = int(ns) if ns.isdigit() else len(row["slices"])
            row["primary_slice"] = row["slices"][0] if row["slices"] else ""
            for k in ("label", "kind", "layer", "ideology", "ein", "notes", "logo", "country"):
                row[k] = (row.get(k) or "").strip()
            nodes[row["id"]] = row

    edges = []
    with open(EDGES_CSV, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f)):
            row["idx"] = i
            row["slices"] = split_multi(row.get("slices"))
            row["source_urls"] = split_multi(row.get("source_url"))
            row["directed_raw"] = row.get("directed", "")
            row["directed"] = to_bool(row.get("directed"))
            for k in ("relation", "layer", "confidence", "label", "evidence", "receipt"):
                row[k] = (row.get(k) or "").strip()
            edges.append(row)

    with open(POSITIONS_JSON, encoding="utf-8") as f:
        positions = json.load(f)

    return nodes, edges, positions


def domain(url):
    """Host for a URL, lower-cased, without a leading 'www.'."""
    host = urlparse(url.strip()).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or url.strip()


def label_of(nodes, node_id, width=None):
    text = nodes[node_id]["label"] if node_id in nodes else node_id
    if width and len(text) > width:
        text = text[: width - 1] + "…"
    return text


def build_adjacency(edges, node_ids=None, directed=False):
    """dict node -> set(neighbours).  Undirected by default."""
    adj = defaultdict(set)
    if node_ids:
        for n in node_ids:
            adj[n]
    for e in edges:
        s, t = e["source"], e["target"]
        adj[s].add(t)
        if directed:
            adj[t]
        else:
            adj[t].add(s)
    return adj


def components(adj):
    """Connected components of an undirected adjacency, largest first."""
    seen, comps = set(), []
    for start in adj:
        if start in seen:
            continue
        comp, stack = set(), [start]
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            comp.add(n)
            stack.extend(adj[n] - seen)
        comps.append(comp)
    comps.sort(key=len, reverse=True)
    return comps


def bfs_reach(adj, start, max_depth):
    """dict node -> hop distance for nodes within max_depth of start (start excluded)."""
    depth = {start: 0}
    q = deque([start])
    while q:
        n = q.popleft()
        if depth[n] >= max_depth:
            continue
        for m in adj[n]:
            if m not in depth:
                depth[m] = depth[n] + 1
                q.append(m)
    depth.pop(start, None)
    return depth


def betweenness(adj):
    """Brandes betweenness centrality for an unweighted undirected graph.

    Returns raw scores halved, since each unordered pair is otherwise counted
    twice.  Only relative values matter for ranking.
    """
    bc = dict.fromkeys(adj, 0.0)
    for s in adj:
        stack, preds, sigma, dist = [], defaultdict(list), defaultdict(int), {}
        sigma[s], dist[s] = 1, 0
        q = deque([s])
        while q:
            v = q.popleft()
            stack.append(v)
            for w in adj[v]:
                if w not in dist:
                    dist[w] = dist[v] + 1
                    q.append(w)
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    preds[w].append(v)
        delta = defaultdict(float)
        while stack:
            w = stack.pop()
            for v in preds[w]:
                delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
            if w != s:
                bc[w] += delta[w]
    return {n: v / 2 for n, v in bc.items()}


def rank(scores):
    """dict node -> 1-based rank, highest score first."""
    ordered = sorted(scores, key=lambda n: -scores[n])
    return {n: i + 1 for i, n in enumerate(ordered)}


def write_csv(topic, name, rows, header):
    out_dir = os.path.join(OUT_DIR, topic)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(["" if v is None else v for v in r])
    return os.path.relpath(path, HERE)


def _cell(v):
    if isinstance(v, float):
        if abs(v) >= 1e6:
            return f"{v:,.0f}"
        s = f"{v:,.2f}".rstrip("0").rstrip(".")
        return s if s else "0"
    return str("" if v is None else v).replace("|", "\\|").replace("\n", " ")


def md_table(rows, header, top=None):
    rows = list(rows)
    if top is not None:
        rows = rows[:top]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for r in rows:
        lines.append("| " + " | ".join(_cell(v) for v in r) + " |")
    return "\n".join(lines)


def pct(part, whole, digits=0):
    return f"{(part / whole * 100):.{digits}f}%" if whole else "n/a"


def heading(text, level=2):
    print("\n" + "#" * level + " " + text + "\n")


def saved(paths):
    print("\nWrote: " + ", ".join(paths))
