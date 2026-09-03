"""geography.py - Where are the people and organisations based?

Questions
1. What does the declared `country` column say, by node kind?
2. How much location can be recovered when `country` is blank, and by which
   method: US EIN, US 501(c) status text, a city or region named in the notes,
   or a "based in X" phrase?
3. Which foreign states are organisations *tied to*? (reported separately;
   a tie is not a base)
4. Which countries appear in which research slice?

Every inferred row carries `method` and `matched_text` so it can be audited.
Bare country names are deliberately NOT used as evidence of location: a
"Honduras Solidarity Network" is a US group about Honduras.

Run: python3 geography.py  ->  analysis/geography/*.csv
"""
import re
from collections import Counter, defaultdict

import common as C

TOPIC = "geography"

# (regex, place, country) - cities and sub-national regions only.
PLACES = [
    (r"\bNYC\b|\bNew York\b|\bBrooklyn\b|\bBronx\b|\bManhattan\b|\bHarlem\b|\bQueens\b", "New York", "US"),
    (r"\bChicago\b", "Chicago", "US"),
    (r"\bPittsburgh\b", "Pittsburgh", "US"),
    (r"\bDenver\b|\bColorado\b", "Colorado", "US"),
    (r"\bLos Angeles\b", "Los Angeles", "US"),
    (r"\bOakland\b|\bSan Francisco\b|\bBay Area\b|\bBerkeley\b", "SF Bay Area", "US"),
    (r"\bPhiladelphia\b|\bPhilly\b", "Philadelphia", "US"),
    (r"\bBoston\b|\bMassachusetts\b|\bAmherst\b", "Massachusetts", "US"),
    (r"\bDetroit\b|\bMichigan\b", "Michigan", "US"),
    (r"\bAtlanta\b", "Atlanta", "US"),
    (r"\bSeattle\b", "Seattle", "US"),
    (r"\bPortland\b", "Portland", "US"),
    (r"\bMinneapolis\b|\bMinnesota\b", "Minnesota", "US"),
    (r"\bWashington,? D\.?C\b|\bD\.C\.|\bDC address\b|\bDC-based\b", "Washington DC", "US"),
    (r"\bBaltimore\b", "Baltimore", "US"),
    (r"\bOklahoma\b", "Oklahoma", "US"),
    (r"\bLancaster\b", "Lancaster PA", "US"),
    (r"\bErie\b", "Erie PA", "US"),
    (r"\bOhio\b", "Ohio", "US"),
    (r"\bTucson\b|\bPhoenix\b|\bTempe\b|\bArizona\b|\bAZ\b", "Arizona", "US"),
    (r"\bCalifornia\b", "California", "US"),
    (r"\bTexas\b|\bHouston\b|\bAustin\b", "Texas", "US"),
    (r"\bMiami\b|\bFlorida\b", "Florida", "US"),
    (r"\bNew Orleans\b|\bNOLA\b|\bLouisiana\b", "New Orleans", "US"),
    (r"\bSt\.? Louis\b|\bFerguson\b|\bMissouri\b", "St Louis", "US"),
    (r"\bMilwaukee\b|\bWisconsin\b", "Wisconsin", "US"),
    (r"\bNew Jersey\b", "New Jersey", "US"),
    (r"\bVermont\b", "Vermont", "US"),
    (r"\bAlbuquerque\b|\bNew Mexico\b", "New Mexico", "US"),
    (r"\bPuerto Rico\b|\bSan Juan\b", "Puerto Rico", "US"),
    (r"\bBerlin\b|\bHamburg\b|\bFrankfurt\b", "Berlin", "Germany"),
    (r"\bLondon\b", "London", "UK"),
    (r"\bCaracas\b", "Caracas", "Venezuela"),
    (r"\bHavana\b|\bLa Habana\b", "Havana", "Cuba"),
    (r"\bManagua\b", "Managua", "Nicaragua"),
    (r"\bTehran\b", "Tehran", "Iran"),
    (r"\bToronto\b|\bMontreal\b|\bVancouver\b|\bOttawa\b", "Canada", "Canada"),
    (r"\bMexico City\b|\bChiapas\b|\bOaxaca\b|\bTijuana\b", "Mexico", "Mexico"),
    (r"\bPort-au-Prince\b", "Port-au-Prince", "Haiti"),
    (r"\bTegucigalpa\b", "Tegucigalpa", "Honduras"),
    (r"\bBogot[aá]\b", "Bogota", "Colombia"),
    (r"\bGaza\b|\bWest Bank\b|\bRamallah\b|\bBethlehem\b", "Palestine", "Palestine"),
    (r"\bTel Aviv\b|\bJerusalem\b|\bHaifa\b", "Israel", "Israel"),
    (r"\bDar es Salaam\b", "Dar es Salaam", "Tanzania"),
    (r"\bS[aã]o Paulo\b|\bRio de Janeiro\b|\bBras[ií]lia\b", "Brazil", "Brazil"),
    (r"\bJohannesburg\b|\bCape Town\b", "South Africa", "South Africa"),
    (r"\bShanghai\b|\bBeijing\b", "China", "China"),
    (r"\bMoscow\b", "Moscow", "Russia"),
    (r"\bAthens\b", "Athens", "Greece"),
    (r"\bMadrid\b|\bBarcelona\b", "Spain", "Spain"),
    (r"\bBuenos Aires\b", "Buenos Aires", "Argentina"),
    (r"\bManila\b", "Manila", "Philippines"),
    (r"\bHarare\b", "Harare", "Zimbabwe"),
    (r"\bCopenhagen\b", "Copenhagen", "Denmark"),
]
PLACE_RE = [(re.compile(p, re.I), place, country) for p, place, country in PLACES]

BASED_RE = re.compile(
    r"\b(?:based in|headquartered in|HQ in|resident(?: in| of)?)\s+([A-Z][\w.]+(?:\s[A-Z][\w.]+)?)"
    r"|([A-Z][\w.]+)-based\b"
    r"|([A-Z][\w.]+)-resident\b"
)
COUNTRY_WORDS = {
    "US": "US", "U.S.": "US", "USA": "US", "United States": "US", "American": "US",
    "German": "Germany", "Germany": "Germany", "UK": "UK", "British": "UK", "Britain": "UK",
    "Venezuela": "Venezuela", "Venezuelan": "Venezuela", "Cuba": "Cuba", "Cuban": "Cuba",
    "Iran": "Iran", "Iranian": "Iran", "Nicaragua": "Nicaragua", "China": "China", "Chinese": "China",
    "Canada": "Canada", "Canadian": "Canada", "Mexico": "Mexico", "Mexican": "Mexico",
    "Brazil": "Brazil", "Brazilian": "Brazil", "Palestine": "Palestine", "Palestinian": "Palestine",
    "Israel": "Israel", "Israeli": "Israel", "Tanzania": "Tanzania", "Haiti": "Haiti",
    "Honduras": "Honduras", "Colombia": "Colombia", "Russia": "Russia", "Greece": "Greece",
    "Spain": "Spain", "Argentina": "Argentina", "Philippines": "Philippines", "Zimbabwe": "Zimbabwe",
    "Denmark": "Denmark", "Danish": "Denmark", "Tucson": "US", "NYC": "US", "Boston": "US",
    "Chicago": "US", "Miami": "US", "Berlin": "Germany", "Shanghai": "China",
}
US_501C_RE = re.compile(r"us_501c|501\s?\(c\)\s?\(\d\)|501c\d", re.I)
# A city named next to travel words is a trip, not a base ("Tehran delegation", "visited Havana").
TRAVEL_RE = re.compile(r"delegat|visit|travel|trip\b|attend|tour\b|brigade|march\b|observer|conference|festival|summit|"
                       r"hosted in|meeting|flew|went to|arrived|caravan|inaugurat|election|assembly|congress", re.I)
URL_RE = re.compile(r"https?://\S+")
METHOD_ORDER = ["declared", "ein_us", "us_501c_text", "city_in_notes", "based_phrase", "none"]


def infer_row(n):
    """Return (country, place, method, matched_text, ambiguous) for one node."""
    declared = n["country"]
    if declared:
        return declared, "", "declared", "", ""
    if n["ein"]:
        return "US", "", "ein_us", n["ein"], ""
    text = URL_RE.sub(" ", n["notes"] + " || " + n["label"])
    m = US_501C_RE.search(text)
    if m:
        return "US", "", "us_501c_text", m.group(0), ""
    hits, travel = [], []
    for rx, place, country in PLACE_RE:
        for m in rx.finditer(text):
            ctx = text[max(0, m.start() - 45): m.end() + 45]
            if TRAVEL_RE.search(ctx):
                travel.append(m.group(0))
            else:
                hits.append((place, country, m.group(0)))
                break
    if hits:
        countries = Counter(c for _, c, _ in hits)
        country = countries.most_common(1)[0][0]
        place = "; ".join(sorted({p for p, c, _ in hits if c == country}))
        matched = "; ".join(t for _, _, t in hits)
        return country, place, "city_in_notes", matched, ("yes" if len(countries) > 1 else "")
    m = BASED_RE.search(text)
    if m:
        word = next(g for g in m.groups() if g)
        country = COUNTRY_WORDS.get(word)
        if country:
            return country, word, "based_phrase", m.group(0), ""
        return "", "", "none", "unmapped based-phrase: " + m.group(0), ""
    if travel:
        return "", "", "none", "travel mention only: " + "; ".join(travel[:3]), ""
    return "", "", "none", "", ""


def main():
    nodes, edges, _ = C.load()
    out = []

    C.heading("1. Declared country (the `country` column)")
    declared = Counter((n["country"] or "<blank>", n["kind"]) for n in nodes.values())
    rows = sorted(([c, k, v] for (c, k), v in declared.items()), key=lambda r: (-r[2], r[0]))
    out.append(C.write_csv(TOPIC, "declared_country.csv", rows, ["country", "kind", "nodes"]))
    blank = sum(1 for n in nodes.values() if not n["country"])
    print(f"`country` is blank on {blank} of {len(nodes)} nodes ({C.pct(blank, len(nodes))}).\n")
    by_country = Counter(n["country"] for n in nodes.values() if n["country"])
    print(C.md_table([[c, v] for c, v in by_country.most_common()], ["declared country", "nodes"], top=12))

    C.heading("2. Inferred location where `country` is blank")
    rows, final = [], {}
    method_counts = Counter()
    for nid, n in nodes.items():
        country, place, method, matched, ambiguous = infer_row(n)
        final[nid] = country
        method_counts[method] += 1
        rows.append([nid, n["label"], n["kind"], n["primary_slice"], n["country"], country, place,
                     method, matched, ambiguous])
    rows.sort(key=lambda r: (METHOD_ORDER.index(r[7]), r[5], r[0]))
    out.append(C.write_csv(TOPIC, "inferred_location.csv", rows,
                           ["id", "label", "kind", "primary_slice", "declared_country", "final_country",
                            "place", "method", "matched_text", "ambiguous"]))
    cum, cov_rows = 0, []
    for m in METHOD_ORDER:
        if m == "none":
            continue
        cum += method_counts[m]
        cov_rows.append([m, method_counts[m], cum, C.pct(cum, len(nodes))])
    cov_rows.append(["still unknown", method_counts["none"], "", C.pct(method_counts["none"], len(nodes))])
    out.append(C.write_csv(TOPIC, "coverage.csv", cov_rows, ["method", "nodes_added", "cumulative", "cumulative_share"]))
    print("Coverage by method (applied in this order of precedence):\n")
    print(C.md_table(cov_rows, ["method", "nodes added", "cumulative", "share of all nodes"]))
    unmapped = [f"{r[0]} ({r[8][23:70]})" for r in rows if r[8].startswith("unmapped based-phrase")]
    if unmapped:
        print(f"\nbased-phrase hits left unmapped (review; not counted): {'; '.join(unmapped)}")
    travel_only = [r for r in rows if r[8].startswith("travel mention only")]
    print(f"{len(travel_only)} nodes mention a city only in a travel context (delegation, visit, election...) and were left unlocated, e.g. " +
          ", ".join(f"{r[0]} ({r[8][21:50]})" for r in travel_only[:5]))

    C.heading("3. Final country x kind (declared + inferred)")
    ck = Counter((final[i] or "<unknown>", n["kind"]) for i, n in nodes.items())
    rows = sorted(([c, k, v] for (c, k), v in ck.items()), key=lambda r: (-r[2], r[0]))
    out.append(C.write_csv(TOPIC, "country_by_kind_final.csv", rows, ["country", "kind", "nodes"]))
    fc = Counter(final[i] or "<unknown>" for i in nodes)
    located = sum(v for c, v in fc.items() if c != "<unknown>")
    print(C.md_table([[c, v, C.pct(v, located) if c != "<unknown>" else ""] for c, v in fc.most_common()],
                     ["country (final)", "nodes", "share of located"], top=14))
    us = fc.get("US", 0)
    print(f"\n{located} nodes now have a country; {us} of those ({C.pct(us, located)}) are US.")
    afgj_projects = [e["target"] for e in edges if e["source"] == "afgj" and e["relation"] == "fiscal_sponsor"]
    unknown_proj = [p for p in afgj_projects if not final.get(p)]
    print(f"Of {len(afgj_projects)} AFGJ-sponsored projects, {len(unknown_proj)} still have no location "
          "(fiscal sponsorship by a US 501(c)(3) does not imply the project is US-based).")

    C.heading("4. Countries by research slice (final)")
    sc = defaultdict(Counter)
    for i, n in nodes.items():
        for s in n["slices"]:
            sc[s][final[i] or "<unknown>"] += 1
    rows, summary = [], []
    for s, c in sorted(sc.items(), key=lambda kv: -sum(kv[1].values())):
        t = sum(c.values())
        for country, v in c.most_common():
            rows.append([s, country, v, C.pct(v, t)])
        known = t - c.get("<unknown>", 0)
        summary.append([s, t, C.pct(known, t), "; ".join(f"{k} {v}" for k, v in c.most_common(4) if k != "<unknown>")])
    out.append(C.write_csv(TOPIC, "country_by_slice.csv", rows, ["slice", "country", "nodes", "share_within_slice"]))
    print(C.md_table(summary, ["slice", "nodes", "located", "top countries"]))

    C.heading("5. Tied to foreign states (foreign_tie edges; a tie, not a base)")
    rows = []
    for e in edges:
        if not e["relation"].lower().startswith("foreign"):
            continue
        src, tgt = nodes.get(e["source"]), nodes.get(e["target"])
        state = tgt["country"] if (tgt and tgt["kind"] == "concept" and tgt["country"]) else (tgt["label"] if tgt else e["target"])
        rows.append([e["source"], src["label"] if src else "", src["kind"] if src else "",
                     final.get(e["source"], ""), state, e["label"], e["confidence"], "|".join(e["slices"])])
    rows.sort(key=lambda r: (r[4], r[0]))
    out.append(C.write_csv(TOPIC, "tied_to_states.csv", rows,
                           ["source", "label", "kind", "source_final_country", "tied_to_state", "edge_label",
                            "confidence", "slices"]))
    ts = Counter(r[4] for r in rows)
    print(C.md_table([[s, v, sum(1 for r in rows if r[4] == s and r[3] == 'US')] for s, v in ts.most_common()],
                     ["state", "tie edges", "from US-located nodes"]))
    C.saved(out)


if __name__ == "__main__":
    main()
