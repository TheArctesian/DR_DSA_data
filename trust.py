"""trust.py - How much of this graph should be believed?

Questions
1. What share of edges is confirmed vs inferred, by slice, relation and layer?
2. Do the hub and broker rankings survive when only confirmed edges are kept?
3. What kinds of sources back each edge (official records, government report,
   encyclopedia, advocacy research, news, movement/self-published, social)?
   How many edges rest only on advocacy-research sites?
4. Are the bulk-mined 'associate' edges real relationships or co-mention cliques
   generated from a single article?
5. How much of the graph has quoted evidence text or a receipt URL?
6. Per node: what share of its edges is confirmed?

The domain classification sets at the top are a rough, editable starting point.
Wayback Machine URLs are unwrapped to the archived site's domain before classifying.

Run: python3 trust.py  ->  analysis/trust/*.csv
"""
import re
from collections import Counter, defaultdict

import common as C

TOPIC = "trust"

OFFICIAL_RECORDS = {"projects.propublica.org", "apps.irs.gov", "irs.gov", "home.treasury.gov", "ofac.treasury.gov",
                    "sanctionssearch.ofac.treas.gov", "sec.gov", "efile.fara.gov", "fara.gov", "waysandmeans.house.gov",
                    "congress.gov", "govinfo.gov", "courtlistener.com", "justice.gov", "opencorporates.com",
                    "candid.org", "causeiq.com", "charitynavigator.org", "guidestar.org", "oag.ca.gov",
                    "apps.dos.ny.gov", "ecorp.azcc.gov", "bizfileonline.sos.ca.gov", "search.sunbiz.org"}
GOVERNMENT_REPORTS = {"state.gov", "2017-2021.state.gov", "2009-2017.state.gov", "gov.uk", "bundestag.de",
                      "europarl.europa.eu", "foreign.senate.gov", "judiciary.senate.gov", "hsgac.senate.gov"}
ENCYCLOPEDIC = {"en.wikipedia.org", "de.wikipedia.org", "es.wikipedia.org", "wikipedia.org", "britannica.com"}
ADVOCACY_RESEARCH = {"influencewatch.org", "keywiki.org", "discoverthenetworks.org", "capitalresearch.org",
                     "heritage.org", "networkcontagion.us", "adl.org", "justthenews.com", "ncri.io",
                     "canarymission.org", "washingtonstand.com", "dailysignal.com", "freebeacon.com",
                     "nationalreview.com", "americanthinker.com", "frontpagemag.com", "thefederalist.com",
                     "isgap.org", "counterextremism.com", "memri.org", "splcenter.org", "ngo-monitor.org",
                     "unwatch.org", "stopantisemitism.org", "legal-insurrection.com", "legalinsurrection.com",
                     "dailycaller.com", "washingtonexaminer.com", "nypost.com", "breitbart.com", "foxnews.com",
                     "globalsecurity.org", "newlinesmag.com", "tabletmag.com", "jpost.com", "timesofisrael.com"}
NEWS = {"nytimes.com", "washingtonpost.com", "theguardian.com", "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk",
        "npr.org", "politico.com", "theatlantic.com", "newyorker.com", "wsj.com", "latimes.com", "chicagotribune.com",
        "bloomberg.com", "ft.com", "economist.com", "axios.com", "thehill.com", "huffpost.com", "vice.com",
        "theintercept.com", "tucsonspotlight.org", "tucson.com", "azcentral.com", "colorlines.com", "democracynow.org",
        "commondreams.org", "truthout.org", "thenation.com", "motherjones.com", "dw.com", "spiegel.de", "taz.de",
        "zeit.de", "sueddeutsche.de", "cnn.com", "nbcnews.com", "abcnews.go.com", "cbsnews.com", "usatoday.com",
        "miamiherald.com", "elpais.com", "aljazeera.com", "middleeasteye.net", "mondoweiss.net", "haaretz.com",
        "forward.com", "jta.org", "berklee.edu", "nyu.edu", "findingaids.library.nyu.edu"}
SOCIAL = {"facebook.com", "linkedin.com", "twitter.com", "x.com", "instagram.com", "youtube.com", "medium.com",
          "substack.com", "t.me", "tiktok.com", "vimeo.com", "soundcloud.com"}
MOVEMENT = {"afgj.org", "hatueyproject.org", "peoplesforum.org", "codepink.org", "rosalux.nyc", "rosalux.de",
            "answercoalition.org", "nnoc.org", "revcom.us", "fightbacknews.org", "orinocotribune.com",
            "popularresistance.org", "southbronxunite.org", "nnomy.org", "venezuelasolidaritynetwork.org",
            "peoplesdispatch.org", "thetricontinental.org", "breakthroughnews.org", "liberationnews.org",
            "pslweb.org", "dsausa.org", "jacobin.com", "progressive.international", "grassrootsonline.org",
            "globalexchange.org", "ips-dc.org", "nlg.org", "ccrjustice.org", "ifconews.org", "youthvsapocalypse.org",
            "economichumanrights.org", "worldfellowship.org", "gp.org", "adastra.management", "nateforcongress.com",
            "samidoun.net", "blackallianceforpeace.com", "frso.org", "freedomroad.org", "ydsa.org", "dsafund.org",
            "wfdy.org", "albamovimientos.org", "telesurenglish.net", "venezuelanalysis.com", "cubadebate.cu",
            "granma.cu", "prensa-latina.cu", "presstv.ir", "hispantv.com", "farsnews.ir", "en.mehrnews.com",
            "tasnimnews.com", "irna.ir", "newhorizon.ir", "codepink.salsalabs.org", "act.codepink.org",
            "brechtforum.org", "generalbakerinstitute.org", "progressunityfund.org", "socialgoodfund.org",
            "unitedcommunityfund.org", "utsnyc.edu", "cultureproject.org", "belly-of-the-beast.com"}
WAYBACK_RE = re.compile(r"^https?://web\.archive\.org/web/\d+[a-z_*]*/(.+)$", re.I)


def unwrap(url):
    m = WAYBACK_RE.match(url.strip())
    if not m:
        return url, False
    inner = m.group(1)
    if not inner.lower().startswith("http"):
        inner = "http://" + inner
    return inner, True


def classify(dom):
    if dom in OFFICIAL_RECORDS:
        return "official_records"
    if dom in GOVERNMENT_REPORTS or dom.endswith(".gov"):
        return "government"
    if dom in ENCYCLOPEDIC:
        return "encyclopedic"
    if dom in ADVOCACY_RESEARCH:
        return "advocacy_research"
    if dom in NEWS:
        return "news"
    if dom in SOCIAL:
        return "social"
    if dom in MOVEMENT:
        return "movement_or_self"
    if dom.endswith(".org"):
        return "other_org_site"
    return "other"


def main():
    nodes, edges, _ = C.load()
    out = []
    lab = lambda i, w=None: C.label_of(nodes, i, w)
    confirmed = [e for e in edges if e["confidence"] == "confirmed"]

    # ---- 1. confidence splits -------------------------------------------
    C.heading("1. Confirmed vs inferred")
    print(f"{len(confirmed)} confirmed ({C.pct(len(confirmed), len(edges))}), {len(edges) - len(confirmed)} inferred.\n")
    def split(keyfn, name, min_n=1):
        c = defaultdict(Counter)
        for e in edges:
            for k in keyfn(e):
                c[k][e["confidence"]] += 1
        rows = [[k, sum(v.values()), v["confirmed"], v["inferred"], C.pct(v["confirmed"], sum(v.values()))]
                for k, v in c.items() if sum(v.values()) >= min_n]
        rows.sort(key=lambda r: (-r[1], r[0]))
        out.append(C.write_csv(TOPIC, f"confidence_by_{name}.csv", rows, [name, "edges", "confirmed", "inferred", "confirmed_share"]))
        return rows
    rows = split(lambda e: e["slices"] or ["<none>"], "slice")
    print(C.md_table(rows, ["slice", "edges", "confirmed", "inferred", "confirmed share"]))
    rows = split(lambda e: [e["relation"]], "relation", min_n=5)
    print("\nBy relation (5+ edges):\n")
    print(C.md_table(rows, ["relation", "edges", "confirmed", "inferred", "confirmed share"], top=25))
    rows = split(lambda e: [e["layer"] or "<blank>"], "layer")
    print("\nBy edge layer:\n")
    print(C.md_table(rows, ["layer", "edges", "confirmed", "inferred", "confirmed share"]))

    # ---- 2. confirmed-only rankings ------------------------------------
    C.heading("2. Do the rankings survive on confirmed edges only?")
    adj_full = C.build_adjacency(edges, node_ids=nodes)
    adj_conf = C.build_adjacency(confirmed, node_ids=nodes)
    deg_full = {n: len(adj_full[n]) for n in nodes}
    deg_conf = {n: len(adj_conf[n]) for n in nodes}
    bc_full, bc_conf = C.betweenness(adj_full), C.betweenness(adj_conf)
    r_df, r_dc, r_bf, r_bc = C.rank(deg_full), C.rank(deg_conf), C.rank(bc_full), C.rank(bc_conf)
    rows = [[n, lab(n), nodes[n]["kind"], deg_full[n], deg_conf[n], C.pct(deg_conf[n], deg_full[n]), r_df[n], r_dc[n], r_dc[n] - r_df[n],
             round(bc_full[n], 1), round(bc_conf[n], 1), r_bf[n], r_bc[n]] for n in nodes]
    rows.sort(key=lambda r: r[6])
    out.append(C.write_csv(TOPIC, "confirmed_only_ranks.csv", rows,
                           ["id", "label", "kind", "degree_full", "degree_confirmed", "confirmed_share", "degree_rank_full",
                            "degree_rank_confirmed", "rank_shift", "betweenness_full", "betweenness_confirmed",
                            "betweenness_rank_full", "betweenness_rank_confirmed"]))
    print("Top 20 hubs on the full graph, with confirmed-only figures:\n")
    print(C.md_table([[r[1][:34], r[3], r[4], r[5], r[6], r[7], r[11], r[12]] for r in rows],
                     ["node", "deg full", "deg conf.", "kept", "rank full", "rank conf.", "betw. rank full", "betw. rank conf."], top=20))
    drops = [r for r in rows[:40] if r[3] >= 5 and r[4] <= 0.4 * r[3]]
    if drops:
        print("\nTop-40 nodes that lose 60%+ of their neighbours without inferred edges: " +
              ", ".join(f"{r[1]} ({r[3]}->{r[4]})" for r in drops))
    isolated_conf = sum(1 for n in nodes if deg_full[n] > 0 and deg_conf[n] == 0)
    print(f"\n{isolated_conf} nodes have edges in the full graph but none once inferred edges are removed.")

    # ---- 3. source types per edge ---------------------------------------
    C.heading("3. What kind of source backs each edge")
    rows, type_by_slice, unclassified = [], defaultdict(Counter), Counter()
    tally = Counter()
    for e in edges:
        doms, types, wayback = [], set(), 0
        for u in e["source_urls"]:
            inner, wb = unwrap(u)
            wayback += wb
            d = C.domain(inner)
            doms.append(d)
            t = classify(d)
            types.add(t)
            if t in ("other", "other_org_site"):
                unclassified[d] += 1
        has_official = "official_records" in types
        only_adv = types == {"advocacy_research"}
        only_enc = types == {"encyclopedic"}
        only_mov = types <= {"movement_or_self", "social", "other_org_site"} and bool(types)
        tally["has_official"] += has_official
        tally["only_advocacy"] += only_adv
        tally["only_encyclopedic"] += only_enc
        tally["only_movement_or_self"] += only_mov
        tally["any_wayback"] += bool(wayback)
        for s in e["slices"] or ["<none>"]:
            type_by_slice[s]["edges"] += 1
            type_by_slice[s]["has_official"] += has_official
            type_by_slice[s]["only_advocacy"] += only_adv
            type_by_slice[s]["only_encyclopedic"] += only_enc
            type_by_slice[s]["only_movement_or_self"] += only_mov
        rows.append([e["idx"], e["source"], e["target"], e["relation"], e["confidence"], "|".join(e["slices"]),
                     "|".join(doms), "|".join(sorted(types)), int(has_official), int(only_adv), int(only_enc), int(only_mov), wayback])
    out.append(C.write_csv(TOPIC, "edge_source_types.csv", rows,
                           ["edge_idx", "source", "target", "relation", "confidence", "slices", "domains", "source_types",
                            "has_official_record", "only_advocacy_research", "only_encyclopedic", "only_movement_or_self", "wayback_urls"]))
    srows = [[s, c["edges"], C.pct(c["has_official"], c["edges"]), C.pct(c["only_advocacy"], c["edges"]),
              C.pct(c["only_encyclopedic"], c["edges"]), C.pct(c["only_movement_or_self"], c["edges"])]
             for s, c in sorted(type_by_slice.items(), key=lambda kv: -kv[1]["edges"])]
    out.append(C.write_csv(TOPIC, "source_types_by_slice.csv", srows,
                           ["slice", "edges", "has_official_record", "only_advocacy_research", "only_encyclopedic", "only_movement_or_self"]))
    n = len(edges)
    print(f"Across all {n} edges: {C.pct(tally['has_official'], n)} cite an official record (990s, Treasury, IRS, Congress); "
          f"{C.pct(tally['only_advocacy'], n)} rest only on advocacy-research sites; {C.pct(tally['only_encyclopedic'], n)} only on Wikipedia; "
          f"{C.pct(tally['only_movement_or_self'], n)} only on the movement's own or social sites; {C.pct(tally['any_wayback'], n)} use a Wayback capture.\n")
    print(C.md_table(srows, ["slice", "edges", "official record", "only advocacy", "only Wikipedia", "only movement/self"]))
    print("\nMost-cited domains left unclassified (extend the sets at the top of trust.py): " +
          ", ".join(f"{d} {c}" for d, c in unclassified.most_common(12)))

    # ---- 4. mined cliques ------------------------------------------------
    C.heading("4. Are the bulk-mined edges co-mention cliques?")
    mined = [e for e in edges if "_mined" in e["slices"]]
    groups = defaultdict(list)
    for e in mined:
        groups[e["source_urls"][0] if e["source_urls"] else "<none>"].append(e)
    rows = []
    for url, es in groups.items():
        ns = {x for e in es for x in (e["source"], e["target"])}
        k = len(ns)
        complete = len(es) == k * (k - 1) // 2
        rels = Counter(e["relation"] for e in es)
        rows.append([url, C.domain(url), len(es), k, int(complete), "; ".join(f"{r} {c}" for r, c in rels.most_common(3)),
                     "; ".join(lab(x, 22) for x in sorted(ns)[:8])])
    rows.sort(key=lambda r: (-r[2], r[0]))
    out.append(C.write_csv(TOPIC, "mined_groups.csv", rows, ["url", "domain", "edges", "distinct_nodes", "complete_clique", "relations", "nodes"]))
    big = [r for r in rows if r[2] >= 3]
    print(f"{len(mined)} _mined edges come from {len(groups)} distinct URLs. {len(big)} URLs yield 3+ edges each, "
          f"accounting for {sum(r[2] for r in big)} edges ({C.pct(sum(r[2] for r in big), len(mined))} of mined); "
          f"{sum(1 for r in big if r[4])} of those groups are complete cliques (everyone linked to everyone).\n")
    print(C.md_table([[r[1], r[2], r[3], "yes" if r[4] else "", r[5], r[6][:80]] for r in rows], ["domain", "edges", "nodes", "clique", "relations", "nodes"], top=12))

    # ---- 5. evidence / receipt coverage ----------------------------------
    C.heading("5. Quoted evidence and receipt coverage")
    c = defaultdict(Counter)
    for e in edges:
        for s in e["slices"] or ["<none>"]:
            c[s]["edges"] += 1
            c[s]["evidence"] += bool(e["evidence"])
            c[s]["receipt"] += bool(e["receipt"])
    rows = [[s, v["edges"], v["evidence"], C.pct(v["evidence"], v["edges"]), v["receipt"], C.pct(v["receipt"], v["edges"])]
            for s, v in sorted(c.items(), key=lambda kv: -kv[1]["edges"])]
    out.append(C.write_csv(TOPIC, "evidence_coverage.csv", rows, ["slice", "edges", "with_evidence_text", "share", "with_receipt", "share_receipt"]))
    print(C.md_table(rows, ["slice", "edges", "evidence text", "share", "receipt", "share"]))

    # ---- 6. per-node confidence ------------------------------------------
    C.heading("6. Per-node confidence (share of a node's edges that are confirmed)")
    nc = defaultdict(Counter)
    for e in edges:
        for x in (e["source"], e["target"]):
            nc[x][e["confidence"]] += 1
    rows = [[n, lab(n), nodes[n]["kind"], sum(v.values()), v["confirmed"], v["inferred"], C.pct(v["confirmed"], sum(v.values()))]
            for n, v in nc.items()]
    rows.sort(key=lambda r: -r[3])
    out.append(C.write_csv(TOPIC, "node_confidence.csv", rows, ["id", "label", "kind", "edges", "confirmed", "inferred", "confirmed_share"]))
    print(C.md_table([[r[1][:34], r[2], r[3], r[4], r[5], r[6]] for r in rows], ["node", "kind", "edges", "confirmed", "inferred", "share"], top=25))
    C.saved(out)


if __name__ == "__main__":
    main()
