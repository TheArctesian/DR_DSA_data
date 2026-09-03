"""timeline.py - When was this network active?

Questions
1. Which edges and nodes carry years or year ranges in their labels and notes?
2. How many edges are active per year and per decade?
3. What time span does each research slice cover?
4. Which nodes have the longest documented spans?

Years are extracted from edge labels and node notes only (URLs stripped;
node labels skipped because they hold lifespans like "(1920-2012)").
Ranges such as "FY2015-2022", "1979->1998", "2009-22" and "2019-present" are
expanded; "present" resolves to the latest plain year found anywhere in the data.

Run: python3 timeline.py  ->  analysis/timeline/*.csv
"""
import datetime
import re
import statistics
from collections import Counter, defaultdict

import common as C

TOPIC = "timeline"
URL_RE = re.compile(r"https?://\S+")
Y = r"((?:19|20)\d{2})"
RANGE_RE = re.compile(r"(?:FY\s?)?" + Y + r"\s*(?:-|–|—|→|->|to)\s*(?:FY\s?)?(" + r"(?:19|20)\d{2}|\d{2})(?!\d)")
PRESENT_RE = re.compile(r"(?:FY\s?)?" + Y + r"\s*(?:-|–|—|→|->|to)\s*(?:present|now|current|today|ongoing)", re.I)
FY_SHORT_RE = re.compile(r"\bFY\s?(\d{2})(?!\d)")
YEAR_RE = re.compile(r"(?<![\w$,.])" + Y + r"(?![\d,])")  # no letters/digits before: skips "L2083"


def clean(text):
    return URL_RE.sub(" ", text or "")


def extract(text, present_year):
    """Return (explicit_years:set, spans:list[(a,b)])."""
    text = clean(text)
    years, spans = set(), []
    for m in PRESENT_RE.finditer(text):
        a = int(m.group(1))
        spans.append((a, present_year))
    for m in RANGE_RE.finditer(text):
        a, b = int(m.group(1)), m.group(2)
        b = int(b) if len(b) == 4 else int(str(a)[:2] + b)
        if b < a:
            a, b = b, a
        if b - a <= 80:
            spans.append((a, b))
    for m in FY_SHORT_RE.finditer(text):
        years.add(2000 + int(m.group(1)))
    for m in YEAR_RE.finditer(text):
        years.add(int(m.group(1)))
    ceiling = present_year + 1
    spans = [(a, min(b, present_year)) for a, b in spans if a <= ceiling]
    years = {y for y in years if y <= ceiling}
    for a, b in spans:
        years.update((a, b))
    return years, spans


def main():
    nodes, edges, _ = C.load()
    out = []
    lab = lambda i, w=None: C.label_of(nodes, i, w)
    this_year = datetime.date.today().year
    texts = [("edge", e["idx"], clean(e["label"])) for e in edges] + [("node", i, clean(n["notes"])) for i, n in nodes.items()]
    all_plain = [int(m.group(1)) for _, _, txt in texts for m in YEAR_RE.finditer(txt)]
    plausible = [y for y in all_plain if y <= this_year + 1]
    present = max(plausible) if plausible else this_year
    bogus = [(scope, i, m.group(1)) for scope, i, txt in texts for m in YEAR_RE.finditer(txt) if int(m.group(1)) > this_year + 1]
    print(f"'present' resolves to {present} (latest plausible plain year in the data; ceiling {this_year + 1}).")
    if bogus:
        print(f"Ignored {len(bogus)} year-like tokens after {this_year + 1}: " + ", ".join(f"{s} {i}: {y}" for s, i, y in bogus[:8]))

    # ---- 1. edges ------------------------------------------------------------
    C.heading("1. Years on edges")
    erows, active, mention = [], Counter(), Counter()
    per_slice = defaultdict(list)
    for e in edges:
        years, spans = extract(e["label"], present)
        if not years:
            continue
        lo, hi = min(years), max(years)
        for a, b in spans:
            lo, hi = min(lo, a), max(hi, b)
        for y in range(lo, hi + 1):
            active[y] += 1
        for y in years:
            mention[y] += 1
        for s in e["slices"] or ["<none>"]:
            per_slice[s].append((lo, hi))
        erows.append([e["idx"], e["source"], e["target"], e["relation"], "|".join(e["slices"]), e["confidence"],
                      " ".join(str(y) for y in sorted(years)), lo, hi, hi - lo, "; ".join(f"{a}-{b}" for a, b in spans), e["label"][:100]])
    erows.sort(key=lambda r: (r[7], r[8]))
    out.append(C.write_csv(TOPIC, "edge_years.csv", erows, ["edge_idx", "source", "target", "relation", "slices", "confidence", "years", "min_year", "max_year", "span_years", "ranges", "label"]))
    print(f"{len(erows)} of {len(edges)} edges ({C.pct(len(erows), len(edges))}) carry a year. "
          f"Relations most often undated: " + ", ".join(f"{r} {n}" for r, n in Counter(e["relation"] for e in edges if not extract(e["label"], present)[0]).most_common(5)))

    # ---- 2. nodes ------------------------------------------------------------
    C.heading("2. Years in node notes")
    nrows, nmention = [], Counter()
    for nid, n in nodes.items():
        years, spans = extract(n["notes"], present)
        if not years:
            continue
        lo, hi = min(years), max(years)
        for a, b in spans:
            lo, hi = min(lo, a), max(hi, b)
        for y in years:
            nmention[y] += 1
        nrows.append([nid, n["label"], n["kind"], n["primary_slice"], " ".join(str(y) for y in sorted(years)), lo, hi, hi - lo, "; ".join(f"{a}-{b}" for a, b in spans)])
    nrows.sort(key=lambda r: (-r[7], r[5]))
    out.append(C.write_csv(TOPIC, "node_years.csv", nrows, ["id", "label", "kind", "primary_slice", "years", "min_year", "max_year", "span_years", "ranges"]))
    print(f"{len(nrows)} of {len(nodes)} nodes ({C.pct(len(nrows), len(nodes))}) mention a year in their notes. Longest documented spans:\n")
    print(C.md_table([[r[1][:34], r[2], r[5], r[6], r[7], r[8][:50]] for r in nrows], ["node", "kind", "from", "to", "span", "ranges"], top=12))

    # ---- 3. histogram --------------------------------------------------------
    C.heading("3. Activity by year and decade")
    years_all = sorted(set(active) | set(mention) | set(nmention))
    rows = [[y, active[y], mention[y], nmention[y]] for y in years_all]
    out.append(C.write_csv(TOPIC, "years_histogram.csv", rows, ["year", "edges_active", "edges_mentioning", "nodes_mentioning"]))
    dec = defaultdict(Counter)
    for y in years_all:
        d = f"{y // 10 * 10}s"
        dec[d]["edges_mentioning"] += mention[y]
        dec[d]["nodes_mentioning"] += nmention[y]
        dec[d]["edge_years_active"] += active[y]
    print(C.md_table([[d, v["edges_mentioning"], v["nodes_mentioning"], v["edge_years_active"]] for d, v in sorted(dec.items())],
                     ["decade", "edge mentions", "node mentions", "edge-years active"]))
    recent = [[y, active[y], mention[y], nmention[y]] for y in years_all if y >= present - 12]
    print("\nLast dozen years:\n")
    print(C.md_table(recent, ["year", "edges active", "edges mentioning", "nodes mentioning"]))

    # ---- 4. slice spans ------------------------------------------------------
    C.heading("4. Time span by research slice (edges with a year)")
    total_by_slice = Counter(s for e in edges for s in (e["slices"] or ["<none>"]))
    rows = []
    for s, spans in sorted(per_slice.items(), key=lambda kv: -len(kv[1])):
        los, his = [a for a, _ in spans], [b for _, b in spans]
        rows.append([s, len(spans), C.pct(len(spans), total_by_slice[s]), min(los), int(statistics.median(los)), int(statistics.median(his)), max(his)])
    out.append(C.write_csv(TOPIC, "slice_span.csv", rows, ["slice", "dated_edges", "share_dated", "earliest", "median_start", "median_end", "latest"]))
    print(C.md_table(rows, ["slice", "dated edges", "share dated", "earliest", "median start", "median end", "latest"]))
    C.saved(out)


if __name__ == "__main__":
    main()
