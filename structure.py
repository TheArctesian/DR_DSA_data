"""structure.py - Hubs, brokers and the shape of the graph.

Questions
1. Is the graph one connected whole? How is degree distributed?
2. Who are the hubs (degree) and who are the brokers (betweenness)?
3. Which nodes bridge several research slices, and which slices connect to which?
4. Is DSA the centre of this network, or is AFGJ? (DSA sits at the layout origin.)
5. How do the compiler's node layers (money, party, state, veneer, ...) connect?
6. Does the saved x/y layout follow the slices, and which nodes sit far from theirs?

Run: python3 structure.py  ->  analysis/structure/*.csv
"""
import math
import statistics
from collections import Counter, defaultdict

import common as C

TOPIC = "structure"


def main():
    nodes, edges, pos = C.load()
    out = []
    lab = lambda i, w=None: C.label_of(nodes, i, w)
    adj = C.build_adjacency(edges, node_ids=nodes)
    edge_count = Counter()
    for e in edges:
        edge_count[e["source"]] += 1
        edge_count[e["target"]] += 1

    # ---- 1. components & degree distribution -----------------------------
    C.heading("1. Connectivity and degree distribution")
    comps = C.components(adj)
    print(f"{len(comps)} components; sizes {[len(c) for c in comps]}.")
    for c in comps[1:]:
        print("  small component: " + ", ".join(f"{i} ({lab(i, 30)})" for i in sorted(c)))
    degs = [len(adj[n]) for n in nodes]
    buckets = Counter("0" if d == 0 else "1" if d == 1 else "2-3" if d <= 3 else "4-9" if d <= 9 else "10-24" if d <= 24 else "25+" for d in degs)
    print("\nUnique-neighbour degree: " + ", ".join(f"{k}: {v}" for k, v in sorted(buckets.items(), key=lambda kv: ["0", "1", "2-3", "4-9", "10-24", "25+"].index(kv[0]))))
    print(f"median {statistics.median(degs):.0f}, mean {statistics.mean(degs):.1f}, max {max(degs)}.")

    # ---- 2. hubs & brokers -----------------------------------------------
    C.heading("2. Hubs (degree) and brokers (betweenness)")
    bc = C.betweenness(adj)
    deg_rank, bc_rank = C.rank({n: len(adj[n]) for n in nodes}), C.rank(bc)
    rows = [[n, nodes[n]["label"], nodes[n]["kind"], nodes[n]["layer"], nodes[n]["primary_slice"], nodes[n]["n_slices"],
             len(adj[n]), edge_count[n], deg_rank[n], round(bc[n], 1), bc_rank[n]] for n in nodes]
    rows.sort(key=lambda r: -r[6])
    out.append(C.write_csv(TOPIC, "degree.csv", rows,
                           ["id", "label", "kind", "layer", "primary_slice", "n_slices", "unique_neighbors",
                            "edge_count", "degree_rank", "betweenness", "betweenness_rank"]))
    print("Top by unique neighbours:\n")
    print(C.md_table([[r[1][:36], r[2], r[6], r[7], r[10]] for r in rows], ["node", "kind", "neighbours", "edges", "betweenness rank"], top=20))
    print("\nTop by betweenness (brokers: nodes that shortest paths must pass through):\n")
    by_bc = sorted(rows, key=lambda r: -r[9])
    print(C.md_table([[r[1][:36], r[2], r[9], r[6], r[8]] for r in by_bc], ["node", "kind", "betweenness", "neighbours", "degree rank"], top=20))
    movers = [r for r in by_bc[:25] if r[8] > 40]
    if movers:
        print("\nBrokers that are NOT hubs (betweenness top-25 but degree rank > 40): " +
              ", ".join(f"{r[1]} (deg rank {r[8]})" for r in movers))

    # ---- 3. bridges & cross-slice matrix ---------------------------------
    C.heading("3. Slice bridges and the cross-slice matrix")
    br = [r for r in rows if r[5] >= 2]
    br.sort(key=lambda r: (-r[5], -r[6]))
    out.append(C.write_csv(TOPIC, "bridges.csv", [[r[0], r[1], r[2], r[5], "|".join(nodes[r[0]]["slices"]), r[6], r[9]] for r in br],
                           ["id", "label", "kind", "n_slices", "slices", "unique_neighbors", "betweenness"]))
    print(f"{len(br)} nodes appear in 2+ slices; {sum(1 for r in br if r[5] >= 3)} in 3+:\n")
    print(C.md_table([[r[1][:34], r[2], r[5], "|".join(nodes[r[0]]["slices"]), r[6]] for r in br if r[5] >= 3],
                     ["node", "kind", "slices", "which", "neighbours"]))
    slices = sorted({n["primary_slice"] or "<none>" for n in nodes.values()})
    mat = defaultdict(Counter)
    for e in edges:
        a = nodes[e["source"]]["primary_slice"] or "<none>"
        b = nodes[e["target"]]["primary_slice"] or "<none>"
        mat[a][b] += 1
        if a != b:
            mat[b][a] += 1
    out.append(C.write_csv(TOPIC, "cross_slice_matrix.csv", [[s] + [mat[s][t] for t in slices] for s in slices], ["primary_slice"] + slices))
    pairs = Counter()
    for e in edges:
        a = nodes[e["source"]]["primary_slice"] or "<none>"
        b = nodes[e["target"]]["primary_slice"] or "<none>"
        if a != b:
            pairs[tuple(sorted((a, b)))] += 1
    within = sum(1 for e in edges if (nodes[e["source"]]["primary_slice"] == nodes[e["target"]]["primary_slice"]))
    print(f"\n{within} edges stay within one primary slice, {len(edges) - within} cross slices. Busiest crossings:\n")
    print(C.md_table([[a, b, n] for (a, b), n in pairs.most_common(12)], ["slice A", "slice B", "edges"]))

    # ---- 4. DSA vs AFGJ --------------------------------------------------
    C.heading("4. Is DSA the centre? DSA vs AFGJ vs the top broker")
    top_broker = by_bc[0][0]
    focus = ["dsa", "afgj"] + ([top_broker] if top_broker not in ("dsa", "afgj") else [])
    rows = []
    for n in focus:
        if n not in nodes:
            continue
        one, two = C.bfs_reach(adj, n, 1), C.bfs_reach(adj, n, 2)
        rows.append([n, lab(n, 40), nodes[n]["layer"], len(adj[n]), deg_rank[n], round(bc[n], 1), bc_rank[n],
                     len(one), len(two), C.pct(len(two), len(nodes) - 1), nodes[n]["n_slices"],
                     f"({pos[n]['x']}, {pos[n]['y']})"])
    out.append(C.write_csv(TOPIC, "dsa_vs_afgj.csv", rows,
                           ["id", "label", "layer", "neighbours", "degree_rank", "betweenness", "betweenness_rank",
                            "reach_1hop", "reach_2hop", "reach_2hop_share", "n_slices", "layout_xy"]))
    print(C.md_table(rows, ["id", "label", "layer", "neigh.", "deg rank", "betw.", "betw. rank", "1-hop", "2-hop", "2-hop share", "slices", "layout x,y"]))
    print("\nDSA is at the layout origin, but the graph's structural centre is whoever tops the ranks above.")

    # ---- 5. layer x layer ------------------------------------------------
    C.heading("5. How the compiler's node layers connect (edge counts)")
    layers = sorted({n["layer"] or "<none>" for n in nodes.values()})
    lm = defaultdict(Counter)
    for e in edges:
        a, b = nodes[e["source"]]["layer"] or "<none>", nodes[e["target"]]["layer"] or "<none>"
        lm[a][b] += 1
        if a != b:
            lm[b][a] += 1
    out.append(C.write_csv(TOPIC, "layer_matrix.csv", [[l] + [lm[l][m] for m in layers] for l in layers], ["node_layer"] + layers))
    print(C.md_table([[l] + [lm[l][m] for m in layers] for l in layers], ["layer"] + layers))
    print("\nRead: row layer x column layer = edges between nodes of those layers (symmetric; diagonal = within-layer).")

    # ---- 6. layout vs slices ---------------------------------------------
    C.heading("6. Does the saved layout follow the slices?")
    K = 6
    ids = list(nodes)
    own = {i: (nodes[i]["primary_slice"] or "<none>") for i in ids}
    by_slice = defaultdict(list)
    for i in ids:
        by_slice[own[i]].append(i)
    cent = {s: (statistics.mean(pos[i]["x"] for i in m), statistics.mean(pos[i]["y"] for i in m)) for s, m in by_slice.items()}
    dist = lambda i, s: math.hypot(pos[i]["x"] - cent[s][0], pos[i]["y"] - cent[s][1])
    knn_same, knn_major = {}, {}
    for i in ids:
        x, y = pos[i]["x"], pos[i]["y"]
        near = sorted(((pos[j]["x"] - x) ** 2 + (pos[j]["y"] - y) ** 2, j) for j in ids if j != i)[:K]
        knn_same[i] = sum(1 for _, j in near if own[j] == own[i]) / K
        knn_major[i] = Counter(own[j] for _, j in near).most_common(1)[0][0]
    node_rows, slice_rows = [], []
    for s, members in by_slice.items():
        ds = [dist(i, s) for i in members]
        mu, sd = statistics.mean(ds), (statistics.pstdev(ds) or 1.0)
        for i in members:
            node_rows.append([i, lab(i), s, pos[i]["x"], pos[i]["y"], round(dist(i, s)), round((dist(i, s) - mu) / sd, 2),
                              round(knn_same[i], 2), knn_major[i]])
        agree = sum(1 for i in members if knn_major[i] == s)
        slice_rows.append([s, len(members), round(cent[s][0]), round(cent[s][1]), round(mu),
                           round(statistics.mean(knn_same[i] for i in members), 2), agree, C.pct(agree, len(members))])
    slice_rows.sort(key=lambda r: -r[1])
    out.append(C.write_csv(TOPIC, "layout_by_slice.csv", slice_rows,
                           ["primary_slice", "nodes", "centroid_x", "centroid_y", "mean_dist_to_centroid",
                            f"mean_share_of_{K}_nearest_in_same_slice", "knn_majority_agrees", "agree_share"]))
    node_rows.sort(key=lambda r: (r[7], -r[6]))
    out.append(C.write_csv(TOPIC, "layout_outliers.csv", node_rows,
                           ["id", "label", "primary_slice", "x", "y", "dist_own_centroid", "z_within_slice",
                            f"share_of_{K}_nearest_in_same_slice", "knn_majority_slice"]))
    overall = statistics.mean(knn_same.values())
    expected = sum((len(m) / len(ids)) ** 2 for m in by_slice.values())
    print(f"For each node, the share of its {K} nearest layout neighbours in the same primary slice averages {overall:.2f}; "
          f"random placement would give about {expected:.2f}.\n")
    print(C.md_table(slice_rows, ["slice", "nodes", "cx", "cy", "mean dist", f"same-slice share of {K} nearest", "kNN majority agrees", "share"]))
    print("\nNodes whose layout neighbourhood belongs to a different slice (lowest same-slice share first):\n")
    print(C.md_table([[r[1][:34], r[2], r[3], r[4], r[7], r[8], r[6]] for r in node_rows], ["node", "slice", "x", "y", "same-slice share", "kNN majority", "z"], top=12))
    C.saved(out)


if __name__ == "__main__":
    main()
