"""quality.py - What needs cleaning before any of this is quoted?

Checks
- isolated nodes; nodes referenced by edges but missing (none expected)
- spelling variants in `directed` (yes / true / no)
- blank rates per column, nodes and edges
- `magnitude` mixes units: org revenue in $M vs a 1-6 salience score for people
- placeholder URLs (example.com), non-http URLs, nodes with no source_url
- `n_slices` disagreeing with the `slices` list
- relation naming variants (hyphen vs underscore, `_of` suffixes)
- duplicate labels; blank edge labels
- positions file: missing / extra ids, duplicate coordinates
- compiler caveats embedded in notes (TIER B / context-only)

One issues.csv with severity, scope, id, field, detail; plus blank_rates.csv.

Run: python3 quality.py  ->  analysis/quality/*.csv
"""
import re
from collections import Counter, defaultdict

import common as C

TOPIC = "quality"
CAVEAT_RE = re.compile(r"TIER B|context[- ]only|NEVER in a Cuba total|stale", re.I)


def main():
    nodes, edges, pos = C.load()
    out, issues = [], []
    add = lambda sev, scope, ident, field, detail: issues.append([sev, scope, ident, field, detail])
    lab = lambda i, w=None: C.label_of(nodes, i, w)

    # connectivity
    adj = C.build_adjacency(edges, node_ids=nodes)
    for n in sorted(nodes):
        if not adj[n]:
            add("medium", "node", n, "edges", f"isolated node: {lab(n)}")
    missing = sorted({x for e in edges for x in (e["source"], e["target"]) if x not in nodes})
    for m in missing:
        add("high", "edge", m, "source/target", "edge references an id with no node row")
    for e in edges:
        if e["source"] == e["target"]:
            add("low", "edge", e["idx"], "source/target", "self-loop")

    # directed spellings
    dv = Counter(e["directed_raw"] for e in edges)
    if len(dv) > 2:
        add("low", "file", "datarep_edges.csv", "directed", "mixed spellings: " + ", ".join(f"{k!r} {v}" for k, v in dv.most_common()))

    # blank rates
    brows = []
    node_cols = ["label", "kind", "layer", "ideology", "magnitude", "ein", "source_url", "notes", "logo", "country", "slices"]
    for col in node_cols:
        key = "source_urls" if col == "source_url" else col
        blank = sum(1 for n in nodes.values() if not n[key] and n[key] != 0)
        brows.append(["nodes", col, len(nodes), blank, C.pct(blank, len(nodes))])
    edge_cols = ["relation", "layer", "confidence", "directed", "label", "source_url", "slices", "evidence", "receipt"]
    for col in edge_cols:
        key = "source_urls" if col == "source_url" else ("directed_raw" if col == "directed" else col)
        blank = sum(1 for e in edges if not e[key])
        brows.append(["edges", col, len(edges), blank, C.pct(blank, len(edges))])
    out.append(C.write_csv(TOPIC, "blank_rates.csv", brows, ["table", "column", "rows", "blank", "blank_share"]))
    for t, col, n, blank, share in brows:
        if blank / n > 0.5 and col not in ("ideology", "ein", "logo", "evidence", "receipt", "magnitude"):
            add("medium", "file", f"datarep_{t}.csv", col, f"{share} blank")
    add("info", "file", "datarep_nodes.csv", "country", f"blank on {sum(1 for n in nodes.values() if not n['country'])} of {len(nodes)} nodes; see geography.py for inferred locations")

    # magnitude units
    by_kind = defaultdict(list)
    for n in nodes.values():
        if n["magnitude"] is not None:
            by_kind[n["kind"]].append(n["magnitude"])
    for k, vals in by_kind.items():
        vals.sort()
        add("info", "file", "datarep_nodes.csv", "magnitude", f"{k}: n={len(vals)} min={vals[0]} median={vals[len(vals) // 2]} max={vals[-1]}")
    add("medium", "file", "datarep_nodes.csv", "magnitude", "mixed units: org values look like revenue in $M, person values are a 1-6 salience score; never aggregate across kinds")

    # URLs
    for n in nodes.values():
        if not n["source_urls"]:
            add("low", "node", n["id"], "source_url", "no source URL")
        for u in n["source_urls"]:
            if "example.com" in u:
                add("high", "node", n["id"], "source_url", f"placeholder URL: {u}")
            elif not u.lower().startswith("http"):
                add("low", "node", n["id"], "source_url", f"not an http(s) URL: {u[:60]}")
    for e in edges:
        if not e["source_urls"]:
            add("medium", "edge", e["idx"], "source_url", "edge with no source URL")
        for u in e["source_urls"]:
            if "example.com" in u:
                add("high", "edge", e["idx"], "source_url", f"placeholder URL: {u}")
            elif not u.lower().startswith("http"):
                add("low", "edge", e["idx"], "source_url", f"not an http(s) URL: {u[:60]}")
        if not e["label"]:
            add("low", "edge", e["idx"], "label", f"blank label ({e['source']} -{e['relation']}-> {e['target']})")
        if e["confidence"] not in ("confirmed", "inferred"):
            add("medium", "edge", e["idx"], "confidence", f"unexpected value {e['confidence']!r}")
        if e["directed"] is None:
            add("medium", "edge", e["idx"], "directed", f"unparseable value {e['directed_raw']!r}")

    # n_slices consistency
    for n in nodes.values():
        raw = n.get("n_slices")
        if raw != len(n["slices"]):
            add("medium", "node", n["id"], "n_slices", f"n_slices={raw} but slices lists {len(n['slices'])}")
    # edge slices not on either endpoint
    for e in edges:
        for s in e["slices"]:
            if s == "_mined" or s == "delegations":
                continue
            if s not in nodes[e["source"]]["slices"] and s not in nodes[e["target"]]["slices"]:
                add("low", "edge", e["idx"], "slices", f"slice {s} on edge but on neither endpoint node")

    # relation naming variants
    rels = Counter(e["relation"] for e in edges)
    norm = defaultdict(list)
    for r in rels:
        key = re.sub(r"[-_ ]", "", r.lower())
        key = re.sub(r"(of|by)$", "", key)
        norm[key].append(r)
    for key, variants in norm.items():
        if len(variants) > 1:
            add("low", "file", "datarep_edges.csv", "relation", "naming variants: " + ", ".join(f"{v} ({rels[v]})" for v in sorted(variants)))
    add("info", "file", "datarep_edges.csv", "relation", f"{len(rels)} distinct relation types; {sum(1 for v in rels.values() if v == 1)} used only once")

    # duplicate labels
    dl = defaultdict(list)
    for n in nodes.values():
        dl[n["label"].strip().lower()].append(n["id"])
    for l, ids in dl.items():
        if len(ids) > 1:
            add("low", "node", "|".join(ids), "label", f"duplicate label {l!r}")
    dup_edges = Counter((e["source"], e["target"], e["relation"]) for e in edges)
    for k, v in dup_edges.items():
        if v > 1:
            add("low", "edge", "->".join(k[:2]), "relation", f"{v} edges with same source, target and relation {k[2]}")

    # positions
    extra = sorted(set(pos) - set(nodes))
    missing_pos = sorted(set(nodes) - set(pos))
    for i in missing_pos:
        add("medium", "node", i, "position", "no x/y in positions file")
    for i in extra:
        add("low", "file", "datarep_positions.csv", "id", f"position for unknown node {i}")
    dup_xy = defaultdict(list)
    for i, p in pos.items():
        dup_xy[(p["x"], p["y"])].append(i)
    for xy, ids in dup_xy.items():
        if len(ids) > 1:
            add("low", "node", "|".join(ids), "position", f"identical coordinates {xy}")
    add("info", "file", "datarep_positions.csv", "format", "file is JSON despite the .csv extension")

    # compiler caveats
    for n in nodes.values():
        m = CAVEAT_RE.search(n["notes"])
        if m:
            add("info", "node", n["id"], "notes", f"compiler caveat in notes: {m.group(0)!r} - {n['notes'][:90]}")

    sev_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    issues.sort(key=lambda r: (sev_order[r[0]], r[1], str(r[2])))
    out.append(C.write_csv(TOPIC, "issues.csv", issues, ["severity", "scope", "id", "field", "detail"]))

    C.heading("Data quality summary")
    sc = Counter(r[0] for r in issues)
    print(C.md_table([[s, sc[s]] for s in ("high", "medium", "low", "info")], ["severity", "issues"]))
    by_field = Counter((r[0], r[3]) for r in issues)
    print("\nBy severity and field:\n")
    print(C.md_table([[s, f, n] for (s, f), n in sorted(by_field.items(), key=lambda kv: (sev_order[kv[0][0]], -kv[1]))], ["severity", "field", "count"]))
    print("\nHigh and medium items (first 25):\n")
    print(C.md_table([r for r in issues if r[0] in ("high", "medium")], ["severity", "scope", "id", "field", "detail"], top=25))
    print("\nBlank rates:\n")
    print(C.md_table(brows, ["table", "column", "rows", "blank", "share"]))
    C.saved(out)


if __name__ == "__main__":
    main()
