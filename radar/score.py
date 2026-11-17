import argparse
import json
import logging
import os
import re
from datetime import date, timedelta
from pathlib import Path

import anthropic
import httpx

from radar.common import DATA, ROOT, config, http, log
from radar.llm import TopicScore, call_structured, db

SITE_RAW = "https://raw.githubusercontent.com/PZawieja/piotr-zawieja-site/main"
SITE_FEED = "https://goldlayer.dev/writing/feed.xml"
SCORED = DATA / "scored"


def _fetch(url: str) -> str:
    try:
        with http() as c:
            r = c.get(url)
            r.raise_for_status()
            return r.text
    except httpx.HTTPError as exc:
        log.warning("fetch failed %s: %s", url, exc)
        return ""


def _local_site() -> Path | None:
    p = Path(os.environ.get("SITE_REPO", ROOT.parent / "piotr-zawieja-site"))
    return p if (p / "POST_WRITING_GUIDE.md").exists() else None


def editorial_context() -> str:
    site = _local_site()
    guide = (
        (site / "POST_WRITING_GUIDE.md").read_text()
        if site
        else _fetch(f"{SITE_RAW}/POST_WRITING_GUIDE.md")
    )
    backlog = (
        (site / "content/topics-backlog.md").read_text()
        if site
        else _fetch(f"{SITE_RAW}/content/topics-backlog.md")
    )
    published = re.findall(
        r"<item>\s*<title>(.*?)</title>", _fetch(SITE_FEED), re.DOTALL
    )
    drafts = []
    if site:
        for f in sorted((site / "content/drafts").glob("*.md")):
            m = re.search(r'^title:\s*"?(.+?)"?\s*$', f.read_text(), re.MULTILINE)
            drafts.append(m.group(1) if m else f.stem)
    rubric = (ROOT / "config" / "editorial_rubric.md").read_text()
    return (
        f"{rubric}\n\n# Existing coverage (for the gap score)\n\n"
        "## Published posts\n"
        + "\n".join(f"- {t}" for t in published)
        + "\n\n## Drafts\n"
        + "\n".join(f"- {t}" for t in drafts)
        + f"\n\n## Backlog\n{backlog}\n\n# Site post-writing guide\n\n{guide}"
    )


def candidates(week: date, n: int) -> list[dict]:
    cur = db().sql(
        """
        SELECT * FROM fct_topic_weekly_scores
        WHERE week_start = ?
          AND NOT list_contains(?, category)
          AND NOT list_contains(?, COALESCE(primary_tag, 'none'))
        ORDER BY momentum_norm * 25 + spread_norm * 15 DESC, items DESC
        LIMIT ?
        """,
        params=[
            week,
            config("scoring")["excluded_categories"],
            config("scoring")["excluded_tags"],
            n,
        ],
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def evidence(cluster_key: str, week: date) -> list[dict]:
    cur = db().sql(
        """
        SELECT i.source, i.source_kind, i.title, i.url, i.engagement,
               LEFT(COALESCE(i.body, ''), 300) AS body
        FROM fct_items AS i
        INNER JOIN stg_llm__topic_clusters AS t USING (topic_key)
        WHERE t.cluster_key = ? AND i.is_relevant
          AND i.first_seen_date >= ? AND i.first_seen_date < ?
        ORDER BY i.source_kind = 'primary' DESC, i.engagement_pct DESC
        LIMIT 8
        """,
        params=[cluster_key, week, week + timedelta(days=7)],
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def adoption_context() -> str:
    rows = (
        db()
        .sql("""
        SELECT package, last_week, weekly_vs_monthly_run_rate
        FROM fct_package_adoption
        QUALIFY ROW_NUMBER() OVER (PARTITION BY package ORDER BY snapshot_date DESC) = 1
        ORDER BY weekly_vs_monthly_run_rate DESC
    """)
        .fetchall()
    )
    return "\n".join(
        f"- {p}: {w:,} downloads last week, run-rate x{r}" for p, w, r in rows
    )


def final_score(c: dict, s: TopicScore) -> float:
    w = config("scoring")["weights"]
    return round(
        c["momentum_norm"] * w["momentum"]
        + c["spread_norm"] * w["spread"]
        + s.audience_relevance / 10 * w["audience_relevance"]
        + s.practical_applicability / 10 * w["practical_applicability"]
        + s.gap / 10 * w["gap"]
        + s.durability / 10 * w["durability"],
        1,
    )


def score_cluster(c: dict, ev: list[dict], system: list[dict], adoption: str) -> dict:
    ev_text = "\n".join(
        f"- [{e['source']}/{e['source_kind']}] {e['title']} ({e['url']}) "
        f"engagement={e['engagement']} :: {e['body']}"
        for e in ev
    )
    user = (
        f"Topic cluster: {c['cluster_label']} ({c['cluster_key']})\n"
        f"Category: {c['category']} | type: {c['item_type']} | "
        f"items this week: {c['items']} across {c['distinct_sources']} sources | "
        f"momentum percentile: {c['momentum_norm']} | growth vs last week: "
        f"{c['growth']:.2f}\n\nPyPI adoption signals:\n{adoption}\n\n"
        f"Evidence:\n{ev_text}"
    )
    s, usage = call_structured(TopicScore, system, user, effort="medium")
    allowed = {e["url"] for e in ev if e["source_kind"] == "primary"}
    s.primary_sources = [u for u in s.primary_sources if u in allowed]
    if not s.primary_sources and s.verdict == "Write now":
        s.verdict = config("scoring")["no_primary_source_verdict_cap"]
    return {
        **{
            k: c[k]
            for k in (
                "cluster_key",
                "cluster_label",
                "category",
                "primary_tag",
                "item_type",
                "items",
                "distinct_sources",
                "momentum_norm",
                "spread_norm",
                "growth",
            )
        },
        "week_start": c["week_start"].isoformat(),
        "score": final_score(c, s),
        **s.model_dump(),
        "other_evidence": [e["url"] for e in ev if e["url"] not in s.primary_sources],
        "checked_on": date.today().isoformat(),
        "_usage": [
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_input_tokens or 0,
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--week",
        type=date.fromisoformat,
        help="week start (Monday); default = last full week",
    )
    p.add_argument(
        "--limit", type=int, default=config("scoring")["top_clusters_to_score"]
    )
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    today = date.today()
    week = args.week or today - timedelta(days=today.weekday() + 7)
    cands = candidates(week, args.limit)
    log.info("week %s: %d candidate clusters", week, len(cands))
    if not cands:
        return
    system = [
        {
            "type": "text",
            "text": editorial_context(),
            "cache_control": {"type": "ephemeral"},
        }
    ]
    adoption = adoption_context()
    if args.dry_run:
        print(system[0]["text"][:3000], "\n...\n")
        for c in cands[:3]:
            print(c["cluster_label"], evidence(c["cluster_key"], week)[:2])
        return
    results = []
    for c in cands:
        try:
            results.append(
                score_cluster(c, evidence(c["cluster_key"], week), system, adoption)
            )
        except (anthropic.APIError, RuntimeError, ValueError) as exc:
            log.warning("cluster scoring failed: %s", type(exc).__name__)
    tokens = [sum(r["_usage"][i] for r in results) for i in range(3)]
    for r in results:
        r.pop("_usage")
    results.sort(key=lambda r: r["score"], reverse=True)
    SCORED.mkdir(parents=True, exist_ok=True)
    out = SCORED / f"{week.isoformat()}.json"
    out.write_text(json.dumps(results, indent=2, default=str))
    verdicts = {
        v: sum(r["verdict"] == v for r in results)
        for v in ("Write now", "Watch", "Skip")
    }
    log.info(
        "scored %d clusters %s; tokens in=%d out=%d cached=%d -> %s",
        len(results),
        verdicts,
        *tokens,
        out.relative_to(ROOT),
    )


if __name__ == "__main__":
    main()
