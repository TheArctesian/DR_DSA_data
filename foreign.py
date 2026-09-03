"""foreign.py - Ties to foreign states, and what the State Department report cites.

Questions
1. Which nodes have `foreign_tie` edges, to which states, with what confidence?
2. Which organisations or people are tied to two or more states?
3. How do nodes connect to the state concept nodes overall (all relations, not
   just foreign_tie)?
4. What does the `rubio_report` node cite, and how: designation, historical, or
   context?  Which of those does the compiler itself flag as context-only?
5. Which nodes does the compiler place in the 'terror' or 'opposition' layers,
   and through what kinds of edges do other nodes connect to them?

Layer names, relation types and flags are the dataset compiler's labels and are
reproduced here as such, not as findings.

Run: python3 foreign.py  ->  analysis/foreign/*.csv
"""
import re
from collections import Counter, defaultdict

import common as C

TOPIC = "foreign"
CAVEAT_RE = re.compile(r"TIER B|context[- ]only|NEVER in a Cuba total", re.I)


def main():
    nodes, edges, _ = C.load()
    out = []
    lab = lambda i, w=None: C.label_of(nodes, i, w)
    state_name = lambda i: nodes[i]["country"] if (i in nodes and nodes[i]["kind"] == "concept" and nodes[i]["country"]) else C.label_of(nodes, i)

    # ---- 1. foreign_tie matrix -------------------------------------------
    C.heading("1. foreign_tie edges: who is tied to which state")
    ties = [e for e in edges if e["relation"].lower().startswith("foreign")]
    states = sorted({state_name(e["target"]) for e in ties})
    per = defaultdict(lambda: defaultdict(list))
    long_rows = []
    for e in ties:
        st = state_name(e["target"])
        per[e["source"]][st].append(e["confidence"][0].upper())
        long_rows.append([e["source"], lab(e["source"]), nodes[e["source"]]["kind"], nodes[e["source"]]["country"], st,
                          e["label"], e["confidence"], "|".join(e["slices"]), e["source_urls"][0] if e["source_urls"] else ""])
    long_rows.sort(key=lambda r: (r[4], r[0]))
    out.append(C.write_csv(TOPIC, "foreign_ties.csv", long_rows,
                           ["source", "label", "kind", "source_country", "state", "edge_label", "confidence", "slices", "url"]))
    wide = []
    for src, d in per.items():
        wide.append([src, lab(src), nodes[src]["kind"], len(d)] + ["".join(sorted(d[s])) if d[s] else "" for s in states])
    wide.sort(key=lambda r: (-r[3], r[0]))
    out.append(C.write_csv(TOPIC, "foreign_tie_matrix.csv", wide, ["source", "label", "kind", "n_states"] + states))
    st_count = Counter(r[4] for r in long_rows)
    st_conf = defaultdict(Counter)
    for r in long_rows:
        st_conf[r[4]][r[6]] += 1
    print(f"{len(ties)} foreign_tie edges from {len(per)} nodes to {len(states)} states.\n")
    print(C.md_table([[s, n, st_conf[s]["confirmed"], st_conf[s]["inferred"], C.pct(st_conf[s]["confirmed"], n)] for s, n in st_count.most_common()],
                     ["state", "ties", "confirmed", "inferred", "confirmed share"]))

    # ---- 2. multi-state --------------------------------------------------
    C.heading("2. Nodes tied to two or more states")
    multi = [r for r in wide if r[3] >= 2]
    out.append(C.write_csv(TOPIC, "multi_state_nodes.csv", multi, ["source", "label", "kind", "n_states"] + states))
    print(C.md_table([[r[1][:36], r[2], r[3]] + r[4:] for r in multi], ["node", "kind", "states"] + states))
    print("\nCells show one letter per tie: C = confirmed, I = inferred.")

    # ---- 3. all in-edges to state concept nodes --------------------------
    C.heading("3. Everything pointing at a state node (all relations)")
    state_ids = sorted({e["target"] for e in ties} | {i for i, n in nodes.items() if n["kind"] == "concept" and n["country"] and i == n["country"].lower()})
    rows = []
    rel_by_state = defaultdict(Counter)
    for e in edges:
        if e["target"] in state_ids:
            rel_by_state[e["target"]][e["relation"]] += 1
            rows.append([e["target"], state_name(e["target"]), e["source"], lab(e["source"]), nodes[e["source"]]["kind"], e["relation"], e["confidence"], e["label"]])
    rows.sort(key=lambda r: (r[1], r[5], r[2]))
    out.append(C.write_csv(TOPIC, "state_inedges.csv", rows, ["state_id", "state", "source", "source_label", "source_kind", "relation", "confidence", "edge_label"]))
    print(C.md_table([[f"{state_name(s)} ({s})", sum(c.values()), "; ".join(f"{r} {n}" for r, n in c.most_common(5))] for s, c in sorted(rel_by_state.items(), key=lambda kv: -sum(kv[1].values()))],
                     ["state node (id)", "in-edges", "relations"]))

    # ---- 4. Rubio report -------------------------------------------------
    C.heading("4. What the Rubio Cuba Report node cites, and how")
    rr = "rubio_report"
    rows = []
    for e in edges:
        if e["target"] == rr or e["source"] == rr:
            other = e["source"] if e["target"] == rr else e["target"]
            n = nodes[other]
            caveat = CAVEAT_RE.search(n["notes"])
            rows.append([other, n["label"], n["kind"], n["layer"], e["relation"], e["confidence"], e["label"],
                         caveat.group(0) if caveat else "", n["magnitude"]])
    rows.sort(key=lambda r: (r[4], r[1]))
    out.append(C.write_csv(TOPIC, "rubio_citations.csv", rows, ["node", "label", "kind", "node_layer", "relation", "confidence", "edge_label", "compiler_caveat", "magnitude"]))
    by_rel = Counter(r[4] for r in rows)
    flagged = [r for r in rows if r[7]]
    print(f"{len(rows)} edges touch {rr}. By citation type:\n")
    print(C.md_table([[k, v, sum(1 for r in rows if r[4] == k and r[7])] for k, v in by_rel.most_common()], ["relation", "edges", "with compiler caveat"]))
    print(f"\n{len(flagged)} cited nodes carry a compiler caveat (e.g. 'TIER B - context-only, NEVER in a Cuba total'):")
    for r in flagged:
        print(f"  - {r[1]} [{r[4]}] magnitude {r[8]}: {r[7]}")
    desig = [r for r in rows if r[4] == "cited_designation"]
    if desig:
        print("\nNodes cited as designations: " + ", ".join(r[1] for r in desig))

    # ---- 5. terror / opposition layers -----------------------------------
    C.heading("5. Nodes in the compiler's 'terror' and 'opposition' layers")
    flagged_ids = {i for i, n in nodes.items() if n["layer"] in ("terror", "opposition")}
    rows = []
    for i in sorted(flagged_ids):
        n = nodes[i]
        touching = [e for e in edges if e["source"] == i or e["target"] == i]
        rows.append([i, n["label"], n["kind"], n["layer"], n["ideology"], n["country"], "|".join(n["slices"]), len(touching),
                     "; ".join(f"{r} {c}" for r, c in Counter(e["relation"] for e in touching).most_common(4))])
    out.append(C.write_csv(TOPIC, "flagged_layer_nodes.csv", rows, ["id", "label", "kind", "layer", "ideology", "country", "slices", "edges", "relations"]))
    print(C.md_table([[r[1][:40], r[3], r[4], r[7], r[8]] for r in rows], ["node", "layer", "ideology", "edges", "relation types"]))
    erows = []
    for e in edges:
        if e["source"] in flagged_ids or e["target"] in flagged_ids:
            flagged_end = e["source"] if e["source"] in flagged_ids else e["target"]
            other = e["target"] if flagged_end == e["source"] else e["source"]
            erows.append([flagged_end, lab(flagged_end), other, lab(other), nodes[other]["kind"], nodes[other]["layer"], e["relation"], e["confidence"], e["label"], "|".join(e["slices"])])
    erows.sort(key=lambda r: (r[0], r[6], r[2]))
    out.append(C.write_csv(TOPIC, "flagged_layer_edges.csv", erows, ["flagged_node", "flagged_label", "other_node", "other_label", "other_kind", "other_layer", "relation", "confidence", "edge_label", "slices"]))
    rel = Counter(r[6] for r in erows)
    conf = Counter(r[7] for r in erows)
    print(f"\n{len(erows)} edges touch these nodes. Relation types: " + ", ".join(f"{k} {v}" for k, v in rel.most_common()) +
          f". Confidence: confirmed {conf['confirmed']}, inferred {conf['inferred']}.")
    print("Most of these connections are citation edges from the report node, not direct organisational links; check `relation` before reading anything into them.")
    C.saved(out)


if __name__ == "__main__":
    main()
