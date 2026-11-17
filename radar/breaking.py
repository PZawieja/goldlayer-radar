import argparse
import hashlib
import logging
import os
from datetime import date

import duckdb

from radar.common import DATA, config, log

QUERIES = {
    "hn": (
        "SELECT title, url, points FROM '{f}' WHERE points >= ? AND len(matched_keywords) > 0",
        "hn_points",
    ),
}


def spikes(run_date: date) -> list[dict]:
    th = config("scoring")["breaking"]
    out = []
    for source, (sql, key) in QUERIES.items():
        f = DATA / "raw" / run_date.isoformat() / f"{source}.parquet"
        if not f.exists():
            continue
        for title, url, eng in duckdb.sql(sql.format(f=f), params=[th[key]]).fetchall():
            out.append(
                {"source": source, "title": title, "url": url, "engagement": eng}
            )
    gh = DATA / "raw" / run_date.isoformat() / "github.parquet"
    if gh.exists():
        rows = duckdb.sql(
            f"""
            SELECT full_name, html_url, stars,
                   stars / GREATEST(DATE_DIFF('day', CAST(created_at AS DATE), ?), 1) AS spd
            FROM '{gh}'
            WHERE list_has_any(topics, ['dbt', 'duckdb', 'data-engineering', 'iceberg',
                                        'text-to-sql', 'data-quality'])
            """,
            params=[run_date],
        ).fetchall()
        out += [
            {"source": "github", "title": n, "url": u, "engagement": s}
            for n, u, s, spd in rows
            if spd >= th["github_stars_per_day"]
        ]
    return out


def to_row(s: dict, run_date: date) -> dict:
    key = "breaking-" + hashlib.sha1(s["url"].encode()).hexdigest()[:12]
    return {
        "cluster_key": key,
        "cluster_label": s["title"],
        "category": "other",
        "primary_tag": None,
        "item_type": "news",
        "items": 1,
        "distinct_sources": 1,
        "momentum_norm": None,
        "week_start": run_date.isoformat(),
        "checked_on": run_date.isoformat(),
        "score": 0,
        "verdict": "Breaking",
        "breaking": True,
        "why_it_matters": f"{s['source']} spike: {s['engagement']} engagement. "
        "Not LLM-scored yet; full score lands in the weekly run.",
        "other_evidence": [s["url"]],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", type=date.fromisoformat, default=date.today())
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    found = spikes(args.date)
    log.info("%d breaking items", len(found))
    if args.dry_run or not found or not os.environ.get("NOTION_TOKEN"):
        return
    from radar.notion_sync import sync

    created, updated = sync([to_row(s, args.date) for s in found])
    log.info("notion: %d created, %d updated", created, updated)


if __name__ == "__main__":
    main()
