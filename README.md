# goldlayer-radar

A weekly trend radar for AI + analytics/data engineering topics. It collects public signals every day, classifies and clusters them with Claude, and scores each topic for how worth writing about it is on [goldlayer.dev](https://goldlayer.dev).

```
daily   collect.py  ──► data/raw/YYYY-MM-DD/*.parquet ──► breaking.py (rules-only spikes)
weekly  dbt (int_items) ─► classify.py (Haiku, Batches) ─► cluster.py (Sonnet)
        ─► dbt (fct_topic_weekly_scores) ─► score.py (Sonnet) ─► notion_sync.py
```

**Sources:** vendor and expert RSS (dbt, Snowflake, BigQuery, Databricks, DuckDB, SELECT, Monte Carlo, Medium tags), dbt Community Discourse, DEV.to, GitHub (data-focused repo searches with star velocity), Hacker News, Lobsters, Bluesky, Hugging Face papers, and PyPI downloads. Reddit is not used: it no longer grants API access to third-party collectors. Every item must mention a data/SQL/warehouse term; generic AI news is filtered out at collection.

**Score (0–100):** momentum 25 · cross-source spread 15 · audience relevance 20 · practical applicability 20 · coverage gap 10 · durability 10. The first two come from dbt; the rest are judged by an LLM against the site's [post-writing guide](https://github.com/PZawieja/piotr-zawieja-site/blob/main/POST_WRITING_GUIDE.md). A topic with no primary source (docs, release notes, paper, repo) cannot get "Write now".

Scored output goes only to a private Notion database. This repo holds raw public signals and topic labels.

## Run locally

```bash
uv sync
uv run python -m radar.bootstrap
# dbt/profiles.yml is gitignored; CI writes it. Locally: a duckdb profile named
# `radar` with path ../data/radar.duckdb (see .github/workflows/score-weekly.yml)
uv run python -m radar.collect
cd dbt && uv run dbt build --profiles-dir . && cd ..
uv run python -m radar.classify --sync --limit 20   # needs ANTHROPIC_API_KEY
uv run python -m radar.cluster
cd dbt && uv run dbt build --profiles-dir . && cd ..
uv run python -m radar.score --week 2026-11-16
```

Every LLM step has `--dry-run`. dbt must run from `dbt/` because source paths are relative (`../data`).

## Setup

1. Create a Notion internal integration, share a parent page with it, then:
   `NOTION_TOKEN=... uv run python -m radar.notion_sync --setup <parent_page_id>`
2. Add repo secrets: `ANTHROPIC_API_KEY`, `NOTION_TOKEN`, `NOTION_DATA_SOURCE_ID`.

Config lives in `config/`: sources, taxonomy, scoring weights, and the editorial rubric.
