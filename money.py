"""money.py - Who funds whom, how much, and through which chains?

Questions
1. Which edges describe a money flow, and which carry dollar amounts?
2. What do node notes say about money (assets, revenue, cumulative grants)?
3. Starting from the three funding spines (Benjamin estate, Singham, RLS Berlin),
   who is downstream, at what depth, and who is fed by more than one spine?
4. What kinds of projects does AFGJ fiscally sponsor?
5. Which nodes sit in the dataset's 'money' layer or carry an EIN, and how much
   money do the edges say they gave or received?

Amount parsing is heuristic.  The headline figure for an edge is the largest
dollar figure in its label (normally the stated cumulative total); every
figure found is kept in `all_amounts` so the choice can be checked.

Run: python3 money.py  ->  analysis/money/*.csv
"""
import re
from collections import Counter, defaultdict, deque

import common as C

TOPIC = "money"
# Each spine is a set of seed nodes: the funder plus the vehicles they control,
# because the person->vehicle link is often a role edge, not a funding edge.
SPINES = {
    "Benjamin estate": ["alvin_benjamin", "rose_benjamin", "arc_of_justice"],
    "Singham": ["singham", "psf", "jef"],
    "RLS Berlin": ["german_gov", "rls_berlin"],
}
CAVEAT_RE = re.compile(r"TIER B|context[- ]only|NEVER in a Cuba total", re.I)
FLOW_KEYWORDS = ("fund", "grant", "donat", "paid", "pay", "contract", "transfer", "sponsor", "financ")
SPONSOR_KEYWORDS = ("sponsor",)
REVERSED_SUFFIXES = ("_by", "_from")
AMOUNT_RE = re.compile(r"([<>~≈]?)\s*\$\s?(\d[\d,]*(?:\.\d+)?)\s*([KkMmBb])?(?![\w])")
EUR_RE = re.compile(r"(?:EUR|€)\s?(\d[\d,]*(?:\.\d+)?)\s*([KkMmBb])?")
MULT = {"": 1, "k": 1e3, "m": 1e6, "b": 1e9}
URL_RE = re.compile(r"https?://\S+")


def parse_amounts(text):
    found = []
    for m in AMOUNT_RE.finditer(text):
        num = m.group(2).replace(",", "")
        suf = (m.group(3) or "").lower()
        try:
            val = float(num) * MULT[suf]
        except ValueError:
            continue
        found.append({"value": val, "qualifier": m.group(1), "raw": m.group(0).strip(), "pos": m.start()})
    return found


def flags(text):
    t = text.lower()
    f = []
    if any(k in t for k in ("/yr", "/year", "per year", "annual")):
        f.append("per_year")
    if "cumulative" in t or "total" in t or "=" in text:
        f.append("cumulative")
    if re.search(r"\$[\d,.]+[kmb]?\s*[-–]\s*\$", text, re.I):
        f.append("range")
    if re.search(r"[~≈]\s*\$|approx", text, re.I):
        f.append("estimate")
    if re.search(r">\s*\$|\$[\d,.]+[kmb]?\+", text, re.I):
        f.append("lower_bound")
    return "|".join(f)


def fmt_usd(v):
    if v is None:
        return ""
    if v >= 1e9:
        return f"${v / 1e9:.2f}B"
    if v >= 1e6:
        return f"${v / 1e6:.2f}M"
    if v >= 1e3:
        return f"${v / 1e3:.0f}K"
    return f"${v:.0f}"


def is_flow(rel):
    r = rel.lower()
    return any(k in r for k in FLOW_KEYWORDS)


def is_sponsorship(rel):
    r = rel.lower()
    return any(k in r for k in SPONSOR_KEYWORDS)


def oriented(e):
    """(funder, recipient) - relations ending in _by/_from point the other way."""
    if e["relation"].lower().endswith(REVERSED_SUFFIXES):
        return e["target"], e["source"]
    return e["source"], e["target"]


def downstream(seeds, flow):
    seeds = set(seeds)
    out = defaultdict(list)
    for e in flow:
        a, b = oriented(e)
        out[a].append((b, e))
    depth, parent, via = {s: 0 for s in seeds}, {}, {}
    q = deque(seeds)
    while q:
        a = q.popleft()
        for b, e in out[a]:
            if b not in depth:
                depth[b] = depth[a] + 1
                parent[b] = a
                via[b] = e["relation"]
                q.append(b)

    def path(b):
        p = [b]
        while p[-1] not in seeds:
            p.append(parent[p[-1]])
        return list(reversed(p))

    return {b: (d, path(b), via[b]) for b, d in depth.items() if b not in seeds}


def main():
    nodes, edges, _ = C.load()
    out = []
    lab = lambda i, w=None: C.label_of(nodes, i, w)

    # ---- 1. flow edges & amounts ----------------------------------------
    C.heading("1. Money-flow edges and dollar amounts")
    flow = [e for e in edges if is_flow(e["relation"])]
    rel_used = Counter(e["relation"] for e in flow)
    print("Relations treated as money flows: " + ", ".join(f"{r} ({n})" for r, n in rel_used.most_common()))
    reversed_rels = sorted({e["relation"] for e in flow if e["relation"].lower().endswith(REVERSED_SUFFIXES)})
    if reversed_rels:
        print("Reversed (recipient -> funder) relations: " + ", ".join(reversed_rels))
    rows = []
    for e in flow:
        funder, recipient = oriented(e)
        amts = parse_amounts(e["label"])
        headline = max((a["value"] for a in amts), default=None)
        cav = CAVEAT_RE.search(e["label"] + " " + (nodes[recipient]["notes"] if recipient in nodes else ""))
        rows.append([e["idx"], funder, lab(funder), recipient, lab(recipient), e["relation"], e["confidence"],
                     "|".join(e["slices"]), e["label"], headline, fmt_usd(headline),
                     "; ".join(a["raw"] for a in amts), flags(e["label"]) if amts else "",
                     cav.group(0) if cav else "", e["source_urls"][0] if e["source_urls"] else ""])
    rows.sort(key=lambda r: (-(r[9] or 0), r[1]))
    out.append(C.write_csv(TOPIC, "funding_edges.csv", rows,
                           ["edge_idx", "funder", "funder_label", "recipient", "recipient_label", "relation",
                            "confidence", "slices", "label", "headline_usd", "headline_fmt", "all_amounts", "flags",
                            "compiler_caveat", "url"]))
    with_amt = [r for r in rows if r[9]]
    non_sponsor = [e for e in flow if not is_sponsorship(e["relation"])]
    print(f"\n{len(flow)} flow edges ({len(non_sponsor)} excluding any *sponsor* relation); "
          f"{len(with_amt)} carry a dollar figure. Largest first:\n")
    print(C.md_table([[r[2][:28], r[4][:28], r[5], r[6], r[10], r[12], r[13], r[8][:55]] for r in with_amt],
                     ["funder", "recipient", "relation", "conf.", "headline", "flags", "caveat", "label"], top=20))

    # ---- 2. amounts in node notes ---------------------------------------
    C.heading("2. Dollar and euro figures in node notes")
    rows = []
    for nid, n in nodes.items():
        text = URL_RE.sub(" ", n["notes"])
        for a in parse_amounts(text):
            ctx = text[max(0, a["pos"] - 60): a["pos"] + 70].replace("\n", " ").strip()
            rows.append([nid, n["label"], n["kind"], "USD", a["value"], fmt_usd(a["value"]), a["qualifier"], ctx])
        for m in EUR_RE.finditer(text):
            val = float(m.group(1).replace(",", "")) * MULT[(m.group(2) or "").lower()]
            ctx = text[max(0, m.start() - 60): m.start() + 70].replace("\n", " ").strip()
            rows.append([nid, n["label"], n["kind"], "EUR", val, "€" + fmt_usd(val)[1:], "", ctx])
    rows.sort(key=lambda r: -r[4])
    out.append(C.write_csv(TOPIC, "node_amounts.csv", rows,
                           ["id", "label", "kind", "currency", "value", "value_fmt", "qualifier", "context"]))
    print(f"{len(rows)} figures on {len({r[0] for r in rows})} nodes. Largest:\n")
    print(C.md_table([[r[1][:30], r[3], r[5], r[7][:90]] for r in rows], ["node", "cur", "value", "context"], top=15))

    # ---- 3. chains from the spines --------------------------------------
    C.heading("3. Funding chains from the three spines")
    modes = {"funding_only": non_sponsor, "incl_sponsorship": flow}
    rows, reach = [], {}
    for mode, subset in modes.items():
        for name, seeds in SPINES.items():
            seeds = [s for s in seeds if s in nodes]
            d = downstream(seeds, subset)
            reach[(mode, name)] = d
            for b, (depth, path, via) in sorted(d.items(), key=lambda kv: (kv[1][0], kv[0])):
                rows.append([mode, name, "|".join(seeds), b, lab(b), nodes[b]["kind"] if b in nodes else "", depth,
                             " -> ".join(path), via])
    out.append(C.write_csv(TOPIC, "chains.csv", rows,
                           ["mode", "spine", "seeds", "recipient", "recipient_label", "recipient_kind",
                            "depth", "path", "last_relation"]))
    print("funding_only = funds/grant/donation relations; incl_sponsorship adds fiscal_sponsor and co-sponsor relations.\n")
    summary = []
    for name, seeds in SPINES.items():
        a = reach.get(("funding_only", name), {})
        b = reach.get(("incl_sponsorship", name), {})
        summary.append([name, "|".join(seeds), len(a), max((v[0] for v in a.values()), default=0), len(b),
                        ", ".join(lab(x, 26) for x, v in sorted(a.items(), key=lambda kv: kv[1][0])[:8])])
    print(C.md_table(summary, ["spine", "seeds", "downstream (funding only)", "max depth", "incl. sponsorship", "first recipients"]))
    multi = defaultdict(dict)
    for (mode, name), d in reach.items():
        if mode != "funding_only":
            continue
        for b, (depth, path, via) in d.items():
            multi[b][name] = depth
    rows = [[b, lab(b), nodes[b]["kind"], len(s), "; ".join(f"{k} d{v}" for k, v in sorted(s.items()))]
            for b, s in multi.items() if len(s) >= 2]
    rows.sort(key=lambda r: (-r[3], r[0]))
    out.append(C.write_csv(TOPIC, "multi_spine_recipients.csv", rows,
                           ["recipient", "label", "kind", "n_spines", "spines_and_depth"]))
    print(f"\nRecipients downstream of two or more spines (funding edges only): {len(rows)}\n")
    print(C.md_table([[r[1][:36], r[2], r[3], r[4]] for r in rows], ["recipient", "kind", "spines", "spine: depth"]))

    # ---- 4. AFGJ sponsorship categories ---------------------------------
    C.heading("4. What AFGJ fiscally sponsors")
    cat_re = re.compile(r"fiscal sponsor\s*\((.+?)\)", re.I)
    cats, proj_rows = Counter(), []
    for e in edges:
        if e["source"] == "afgj" and is_sponsorship(e["relation"]):
            m = cat_re.search(e["label"])
            cat = m.group(1).strip() if m else "<uncategorised>"
            cats[cat] += 1
            proj_rows.append([e["target"], lab(e["target"]), cat, e["confidence"],
                              e["source_urls"][0] if e["source_urls"] else ""])
    proj_rows.sort(key=lambda r: (r[2], r[1]))
    out.append(C.write_csv(TOPIC, "afgj_projects.csv", proj_rows, ["project", "label", "category", "confidence", "url"]))
    rows = [[c, n, C.pct(n, sum(cats.values()))] for c, n in cats.most_common()]
    out.append(C.write_csv(TOPIC, "afgj_sponsorship_categories.csv", rows, ["category", "projects", "share"]))
    print(f"AFGJ fiscally sponsors {sum(cats.values())} nodes in this dataset, in {len(cats)} labelled categories:\n")
    print(C.md_table(rows, ["category", "projects", "share"]))

    # ---- 5. money-layer nodes -------------------------------------------
    C.heading("5. Money-layer nodes (dataset layer='money' or EIN present)")
    given, received, n_out, n_in = Counter(), Counter(), Counter(), Counter()
    for e in flow:
        a, b = oriented(e)
        n_out[a] += 1
        n_in[b] += 1
        amt = max((x["value"] for x in parse_amounts(e["label"])), default=0)
        given[a] += amt
        received[b] += amt
    rows = []
    for nid, n in nodes.items():
        if n["layer"] == "money" or n["ein"] or n_out[nid] or n_in[nid]:
            rows.append([nid, n["label"], n["kind"], n["layer"], n["country"], n["ein"], n["magnitude"],
                         n_out[nid], given[nid] or None, fmt_usd(given[nid]) if given[nid] else "",
                         n_in[nid], received[nid] or None, fmt_usd(received[nid]) if received[nid] else "",
                         n["notes"][:160]])
    rows.sort(key=lambda r: (-(r[8] or 0) - (r[11] or 0), -r[7], r[0]))
    out.append(C.write_csv(TOPIC, "money_nodes.csv", rows,
                           ["id", "label", "kind", "layer", "country", "ein", "magnitude", "flow_edges_out",
                            "given_usd_headline_sum", "given_fmt", "flow_edges_in", "received_usd_headline_sum",
                            "received_fmt", "notes_excerpt"]))
    print(f"{len(rows)} nodes; those with a stated amount given or received:\n")
    print(C.md_table([[r[1][:34], r[2], r[5], r[6], r[7], r[9], r[10], r[12]] for r in rows if r[8] or r[11]],
                     ["node", "kind", "EIN", "magnitude", "out", "given", "in", "received"], top=20))
    print("\n`magnitude` for orgs reads like annual revenue in $M (e.g. RLS Berlin 71 ~ EUR 71.2M); "
          "for people it is a 1-6 salience score. Do not sum the two.")
    C.saved(out)


if __name__ == "__main__":
    main()
