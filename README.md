# DR_DSA_data

A political-network dataset (people, organisations, projects and events, and
the relations between them) plus a set of independent, standard-library-only
Python scripts that analyse it.

## Contents

| File | What it holds |
|---|---|
| `datarep_nodes.csv` | 512 nodes: `id, label, kind, layer, ideology, magnitude, ein, source_url, notes, logo, country, slices, n_slices` |
| `datarep_edges.csv` | 1,059 relations: `source, target, relation, layer, confidence, directed, label, source_url, slices, evidence, receipt` |
| `datarep_positions.csv` | x/y layout coordinates for every node, one JSON object keyed by node id (despite the `.csv` extension) |
| `common.py` | Shared loader and helper functions. Every script below imports this and nothing else outside the standard library. |
| `sources.py`, `geography.py`, `money.py`, `structure.py`, `foreign.py`, `people.py`, `trust.py`, `timeline.py`, `quality.py` | Nine independent analysis scripts, one per topic (see below) |
| `run_all.py` | Runs some or all of the above in sequence |
| `analysis/<topic>/*.csv` | Generated output tables, one subfolder per script |

## Requirements

Python 3.8 or later. No third-party packages — everything runs on the
standard library (`csv`, `json`, `collections`, `re`, `urllib.parse`).

```
python3 --version
```

## Running it

Run scripts from the repository root, since they read `datarep_*.csv` with
paths relative to their own location.

Run everything:

```
python3 run_all.py
```

Run a subset:

```
python3 run_all.py money trust
```

Run any single script on its own — each one is fully independent aside from
`common.py`:

```
python3 sources.py
python3 geography.py
python3 money.py
python3 structure.py
python3 foreign.py
python3 people.py
python3 trust.py
python3 timeline.py
python3 quality.py
```

Each script prints a short markdown-formatted summary to the terminal and
writes its full tables to `analysis/<topic>/*.csv`. Re-running a script
overwrites its own output folder only; the other topics are untouched.

## What each script answers

- **`sources.py`** — Which websites are cited as evidence, and which nodes
  originate the most relationships (e.g. as a fiscal sponsor)?
- **`geography.py`** — Where is each node based? Combines the declared
  `country` column with inferred location (US EIN, 501(c) status text, a
  city named in the notes), each row tagged with its inference method.
- **`money.py`** — Dollar amounts parsed out of funding-related edges and
  node notes; funding chains traced downstream from named funding sources;
  what a fiscal sponsor's sponsored projects are categorised as.
- **`structure.py`** — Degree and betweenness centrality, which nodes bridge
  multiple research "slices", and how well the saved x/y layout matches
  those slices.
- **`foreign.py`** — Edges typed as a tie to a foreign state, and what an
  in-dataset citation-source node cites and how.
- **`people.py`** — Person-to-organisation roles, people who hold roles in
  several organisations (interlocks), event attendance, and family ties.
- **`trust.py`** — Confirmed vs. inferred edges by slice/relation/layer,
  whether hub and broker rankings hold up on confirmed edges only, what kind
  of source backs each edge, and whether bulk-mined edges are genuine
  relationships or single-article co-mention groups.
- **`timeline.py`** — Years and year ranges extracted from edge labels and
  node notes, and activity by year, decade and research slice.
- **`quality.py`** — Data-quality issues: isolated nodes, inconsistent
  field values, blank rates per column, placeholder URLs, and more.

## A note on the data

Several fields in this dataset — the `layer` value `terror`, relations like
`infiltrated`, and phrases in `notes` such as "potential unregistered
foreign agent" — are labels applied by whoever compiled the dataset, not
independently verified facts. The scripts print them as dataset labels and
attach each edge's `confidence` (`confirmed` or `inferred`) wherever
relevant; `trust.py` and `quality.py` are the two scripts most focused on
how much weight each part of the data can bear.
