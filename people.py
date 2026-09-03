"""people.py - Roles, interlocks, events and family ties.

Questions
1. Which people hold roles (officer, director, founder, staff, ...) in which
   organisations, and which are only members?
2. Who holds roles in two or more organisations, and which organisations share
   people (interlocking roles)?
3. Who took part in which events, who took part in several, and who co-attended?
4. Which family (spouse/relative) ties exist, and which organisations do those
   relatives hold roles in?

Run: python3 people.py  ->  analysis/people/*.csv
"""
from collections import Counter, defaultdict
from itertools import combinations

import common as C

TOPIC = "people"
ROLE_KEYWORDS = ("role", "officer", "director", "founder", "president", "secretary", "treasurer", "chair",
                 "board", "staff", "coordinator", "employee", "fellow", "instructor", "organizer", "editor",
                 "leader", "manager", "trustee", "advisor", "adviser", "executive", "spokes",
                 "candidate", "running_mate", "council")
EXACT_ROLES = {"led", "leads", "head", "heads", "headed"}  # exact matches only: 'led' is inside 'traveled_to'
MEMBER_KEYWORDS = ("member", "affiliation", "affiliate")
FAMILY_KEYWORDS = ("spouse", "relative", "married", "sibling", "parent", "child", "family", "daughter", "son", "wife", "husband")
ORG_KINDS = {"org", "project", "concept"}


def tier(rel):
    r = rel.lower()
    if r in EXACT_ROLES or any(k in r for k in ROLE_KEYWORDS):
        return "role"
    if any(k in r for k in MEMBER_KEYWORDS):
        return "member"
    return ""


def main():
    nodes, edges, _ = C.load()
    out = []
    lab = lambda i, w=None: C.label_of(nodes, i, w)
    kind = lambda i: nodes[i]["kind"] if i in nodes else ""

    # ---- 1. roles ----------------------------------------------------------
    C.heading("1. Person -> organisation roles")
    rows, skipped = [], Counter()
    for e in edges:
        t = tier(e["relation"])
        if not t:
            continue
        s, o = e["source"], e["target"]
        if kind(s) == "person" and kind(o) in ORG_KINDS:
            person, org = s, o
        elif kind(o) == "person" and kind(s) in ORG_KINDS:
            person, org = o, s
        else:
            skipped[(kind(s), kind(o))] += 1
            continue
        rows.append([person, lab(person), org, lab(org), kind(org), e["relation"], t, e["label"], e["confidence"], "|".join(e["slices"])])
    rows.sort(key=lambda r: (r[6], r[1], r[3]))
    out.append(C.write_csv(TOPIC, "roles.csv", rows, ["person", "person_label", "org", "org_label", "org_kind", "relation", "tier", "edge_label", "confidence", "slices"]))
    rel_used = Counter((r[5], r[6]) for r in rows)
    print("Relations counted as roles: " + ", ".join(f"{r} ({n})" for (r, t), n in rel_used.most_common() if t == "role"))
    print("Relations counted as membership: " + ", ".join(f"{r} ({n})" for (r, t), n in rel_used.most_common() if t == "member"))
    print(f"\n{sum(1 for r in rows if r[6] == 'role')} role edges and {sum(1 for r in rows if r[6] == 'member')} membership edges link a person to an organisation. "
          f"Skipped {sum(skipped.values())} role/member edges not between a person and an org: " + ", ".join(f"{a}->{b} {n}" for (a, b), n in skipped.most_common()))
    org_people = defaultdict(set)
    for r in rows:
        if r[6] == "role":
            org_people[r[2]].add(r[0])
    print("\nOrganisations with the most people holding roles:\n")
    print(C.md_table([[lab(o, 40), kind(o), len(p), ", ".join(lab(x, 18) for x in sorted(p)[:6])] for o, p in sorted(org_people.items(), key=lambda kv: -len(kv[1]))],
                     ["organisation", "kind", "people", "examples"], top=12))

    # ---- 2. multi-org people & interlocks ---------------------------------
    C.heading("2. People in several organisations, and interlocks")
    person_orgs, person_orgs_all = defaultdict(set), defaultdict(set)
    for r in rows:
        person_orgs_all[r[0]].add(r[2])
        if r[6] == "role":
            person_orgs[r[0]].add(r[2])
    inferred_roles = Counter(r[0] for r in rows if r[6] == "role" and r[8] == "inferred")
    mrows = [[p, lab(p), len(person_orgs[p]), len(person_orgs_all[p]), inferred_roles[p],
              "; ".join(lab(o, 30) for o in sorted(person_orgs[p]))]
             for p in person_orgs_all if len(person_orgs_all[p]) >= 2]
    mrows.sort(key=lambda r: (-r[2], -r[3], r[1]))
    out.append(C.write_csv(TOPIC, "people_multi_org.csv", mrows, ["person", "label", "orgs_with_role", "orgs_incl_membership", "inferred_role_edges", "role_orgs"]))
    print(f"{len(mrows)} people are linked to 2+ organisations (roles or membership); {sum(1 for r in mrows if r[2] >= 2)} hold roles in 2+. "
          "The inferred column counts role edges marked inferred; check roles.csv before quoting any of these.\n")
    print(C.md_table([[r[1][:28], r[2], r[3], r[4], r[5][:90]] for r in mrows if r[2] >= 2], ["person", "role orgs", "incl. member", "inferred", "organisations"], top=20))
    shared = defaultdict(set)
    for p, orgs in person_orgs.items():
        for a, b in combinations(sorted(orgs), 2):
            shared[(a, b)].add(p)
    irows = [[a, lab(a), b, lab(b), len(p), "; ".join(lab(x, 24) for x in sorted(p))] for (a, b), p in shared.items()]
    irows.sort(key=lambda r: (-r[4], r[1], r[3]))
    out.append(C.write_csv(TOPIC, "interlocks.csv", irows, ["org_a", "org_a_label", "org_b", "org_b_label", "shared_people", "people"]))
    print(f"\n{len(irows)} organisation pairs share at least one role-holder. Strongest interlocks:\n")
    print(C.md_table([[r[1][:30], r[3][:30], r[4], r[5][:70]] for r in irows], ["org A", "org B", "shared", "people"], top=15))

    # ---- 3. events -----------------------------------------------------------
    C.heading("3. Events: who took part, who repeats, who co-attended")
    events = sorted(i for i in nodes if i.startswith("ev_"))
    arows, part_events = [], defaultdict(set)
    for e in edges:
        for ev, other in ((e["target"], e["source"]), (e["source"], e["target"])):
            if ev in events and other not in events:
                arows.append([ev, lab(ev), other, lab(other), kind(other), e["relation"], e["confidence"], e["label"]])
                part_events[other].add(ev)
    arows.sort(key=lambda r: (r[0], r[4], r[3]))
    out.append(C.write_csv(TOPIC, "event_attendance.csv", arows, ["event", "event_label", "participant", "participant_label", "participant_kind", "relation", "confidence", "edge_label"]))
    ev_count = Counter(r[0] for r in arows)
    print(C.md_table([[lab(ev, 50), ev_count[ev], "; ".join(f"{r} {n}" for r, n in Counter(x[5] for x in arows if x[0] == ev).most_common(4))] for ev in events],
                     ["event", "participants", "relations"]))
    rep = [[p, lab(p), kind(p), len(evs), "; ".join(lab(x, 34) for x in sorted(evs))] for p, evs in part_events.items() if len(evs) >= 2]
    rep.sort(key=lambda r: (-r[3], r[1]))
    out.append(C.write_csv(TOPIC, "repeat_participants.csv", rep, ["participant", "label", "kind", "events", "which"]))
    print(f"\n{len(rep)} participants appear at 2+ events:\n")
    print(C.md_table([[r[1][:30], r[2], r[3], r[4][:100]] for r in rep], ["participant", "kind", "events", "which"]))
    co = defaultdict(set)
    for ev in events:
        ps = sorted({r[2] for r in arows if r[0] == ev})
        for a, b in combinations(ps, 2):
            co[(a, b)].add(ev)
    crows = [[a, lab(a), b, lab(b), len(evs), "; ".join(lab(x, 30) for x in sorted(evs))] for (a, b), evs in co.items()]
    crows.sort(key=lambda r: (-r[4], r[1], r[3]))
    out.append(C.write_csv(TOPIC, "co_attendance.csv", crows, ["a", "a_label", "b", "b_label", "shared_events", "events"]))
    print(f"\n{len(crows)} co-attendance pairs; {sum(1 for r in crows if r[4] >= 2)} pairs share 2+ events:\n")
    print(C.md_table([[r[1][:26], r[3][:26], r[4], r[5][:80]] for r in crows if r[4] >= 2], ["A", "B", "shared", "events"], top=15))

    # ---- 4. family -----------------------------------------------------------
    C.heading("4. Family ties and the organisations those relatives hold roles in")
    frows = [[e["source"], lab(e["source"]), e["target"], lab(e["target"]), e["relation"], e["label"], e["confidence"]]
             for e in edges if any(k in e["relation"].lower() for k in FAMILY_KEYWORDS)]
    frows.sort(key=lambda r: (r[1], r[3]))
    out.append(C.write_csv(TOPIC, "family.csv", frows, ["a", "a_label", "b", "b_label", "relation", "edge_label", "confidence"]))
    print(C.md_table([[r[1][:26], r[4], r[3][:26], r[5][:60], r[6]] for r in frows], ["A", "relation", "B", "label", "conf."]))
    fam_people = {r[0] for r in frows} | {r[2] for r in frows}
    rrows = [[p, lab(p), o, lab(o), rel, conf] for p in sorted(fam_people) for (o, rel, conf) in sorted({(r[2], r[5], r[8]) for r in rows if r[0] == p and r[6] == "role"})]
    out.append(C.write_csv(TOPIC, "family_roles.csv", rrows, ["person", "label", "org", "org_label", "relation", "confidence"]))
    print(f"\nRoles held by the {len(fam_people)} people in family ties:\n")
    print(C.md_table([[r[1][:26], r[3][:40], r[4], r[5]] for r in rrows], ["person", "organisation", "relation", "confidence"]))
    C.saved(out)


if __name__ == "__main__":
    main()
