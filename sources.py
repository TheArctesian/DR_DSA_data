"""sources.py - Which sources does this dataset rest on?

Two meanings of "source" are covered:
  A. Evidence websites: the source_url citations on edges and nodes.
  B. Originating nodes: the 'source' end of each edge (who the relationship
     is attributed from), versus the 'target' end.

Questions
1. Which websites are cited as evidence for edges? For nodes?
2. How does the evidence mix differ by research slice?
3. How many edges rest on exactly one website, and which sites carry them?
4. Which nodes originate the most relationships, and which receive the most?

Run: python3 sources.py  ->  analysis/sources/*.csv
"""
from collections import Counter, defaultdict

import common as C

TOPIC = "sources"


def main():
    nodes, edges, _ = C.load()
    out = []

    # ---- A1. edge evidence domains --------------------------------------
    C.heading("A1. Evidence websites cited on edges")
    edge_dom = Counter()
    for e in edges:
        for u in e["source_urls"]:
            edge_dom[C.domain(u)] += 1
    total = sum(edge_dom.values())
    rows = [[d, n, C.pct(n, total, 1)] for d, n in edge_dom.most_common()]
    out.append(C.write_csv(TOPIC, "edge_domains.csv", rows, ["domain", "citations", "share"]))
    print(f"{len(edges)} edges carry {total} citations across {len(edge_dom)} domains.\n")
    print(C.md_table(rows, ["domain", "citations", "share"], top=15))

    # ---- A2. node evidence domains --------------------------------------
    C.heading("A2. Evidence websites cited on nodes")
    node_dom = Counter()
    for n in nodes.values():
        for u in n["source_urls"]:
            node_dom[C.domain(u)] += 1
    ntotal = sum(node_dom.values())
    rows = [[d, n, C.pct(n, ntotal, 1)] for d, n in node_dom.most_common()]
    out.append(C.write_csv(TOPIC, "node_domains.csv", rows, ["domain", "citations", "share"]))
    with_url = sum(1 for n in nodes.values() if n["source_urls"])
    print(f"{with_url} of {len(nodes)} nodes cite at least one URL "
          f"({ntotal} citations, {len(node_dom)} domains); {len(nodes) - with_url} nodes cite nothing.\n")
    print(C.md_table(rows, ["domain", "citations", "share"], top=10))

    # ---- A3. evidence mix by slice --------------------------------------
    C.heading("A3. Evidence mix by research slice (edges)")
    by_slice = defaultdict(Counter)
    for e in edges:
        for s in (e["slices"] or ["<none>"]):
            for u in e["source_urls"]:
                by_slice[s][C.domain(u)] += 1
    rows, summary = [], []
    for s, c in sorted(by_slice.items(), key=lambda kv: -sum(kv[1].values())):
        t = sum(c.values())
        for d, n in c.most_common():
            rows.append([s, d, n, C.pct(n, t, 1)])
        top3 = "; ".join(f"{d} {C.pct(n, t)}" for d, n in c.most_common(3))
        summary.append([s, t, len(c), top3])
    out.append(C.write_csv(TOPIC, "domains_by_slice.csv", rows,
                           ["slice", "domain", "citations", "share_within_slice"]))
    print(C.md_table(summary, ["slice", "citations", "distinct domains", "top 3 domains"]))

    # ---- A4. single-source edges ----------------------------------------
    C.heading("A4. Edges resting on a single website")
    n_urls = Counter(len(e["source_urls"]) for e in edges)
    print("Citations per edge: " + ", ".join(f"{k} url -> {v} edges" for k, v in sorted(n_urls.items())))
    single = [e for e in edges if len(e["source_urls"]) == 1]
    sdom = Counter(C.domain(e["source_urls"][0]) for e in single)
    rows = [[d, n, C.pct(n, len(edges), 1)] for d, n in sdom.most_common()]
    out.append(C.write_csv(TOPIC, "single_source_domains.csv", rows,
                           ["domain", "edges_sole_source", "share_of_all_edges"]))
    rows = [[e["idx"], e["source"], e["target"], e["relation"], e["confidence"],
             "|".join(e["slices"]), C.domain(e["source_urls"][0]), e["source_urls"][0]] for e in single]
    out.append(C.write_csv(TOPIC, "single_source_edges.csv", rows,
                           ["edge_idx", "source", "target", "relation", "confidence", "slices", "domain", "url"]))
    print(f"\n{len(single)} of {len(edges)} edges ({C.pct(len(single), len(edges))}) cite exactly one URL. "
          "Sites carrying those edges alone:\n")
    print(C.md_table([[d, n, C.pct(n, len(edges), 1)] for d, n in sdom.most_common()],
                     ["domain", "edges", "share of all edges"], top=10))
    ph_nodes = [n["id"] for n in nodes.values() if any("example.com" in u for u in n["source_urls"])]
    ph_edges = [e["idx"] for e in edges if any("example.com" in u for u in e["source_urls"])]
    if ph_nodes or ph_edges:
        print(f"\nPlaceholder example.com URLs: nodes {ph_nodes or 'none'}; edge rows {ph_edges or 'none'}")

    # ---- B. originating / receiving nodes -------------------------------
    C.heading("B. Originating and receiving nodes (edge 'source' vs 'target')")
    outd, ind = Counter(), Counter()
    out_rel = defaultdict(Counter)
    for e in edges:
        outd[e["source"]] += 1
        ind[e["target"]] += 1
        out_rel[e["source"]][e["relation"]] += 1
    rows = []
    for nid, n in nodes.items():
        o, i = outd[nid], ind[nid]
        rows.append([nid, n["label"], n["kind"], n["country"], o, i, o + i,
                     "; ".join(f"{r} {k}" for r, k in out_rel[nid].most_common(3))])
    rows.sort(key=lambda r: -r[6])
    out.append(C.write_csv(TOPIC, "node_degree.csv", rows,
                           ["id", "label", "kind", "country", "out_edges", "in_edges", "total", "top_out_relations"]))
    top_src = sorted(rows, key=lambda r: -r[4])[:15]
    print("Top originating nodes:\n")
    print(C.md_table([[r[0], r[1][:40], r[2], r[4], C.pct(r[4], len(edges)), r[7]] for r in top_src],
                     ["id", "label", "kind", "out", "share", "top relations"]))
    top_tgt = sorted(rows, key=lambda r: -r[5])[:15]
    print("\nTop receiving nodes:\n")
    print(C.md_table([[r[0], r[1][:40], r[2], r[5], C.pct(r[5], len(edges))] for r in top_tgt],
                     ["id", "label", "kind", "in", "share"]))
    afgj = outd["afgj"]
    print(f"\nAFGJ alone originates {afgj} of {len(edges)} edges ({C.pct(afgj, len(edges))}); "
          f"{out_rel['afgj']['fiscal_sponsor']} of those are fiscal_sponsor edges. "
          f"Without AFGJ the next largest originator is {top_src[1][1]} with {top_src[1][4]}.")
    C.saved(out)


if __name__ == "__main__":
    main()
