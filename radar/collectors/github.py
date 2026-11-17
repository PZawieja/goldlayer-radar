import os
from datetime import timedelta

import pyarrow as pa

from radar.common import config, http, log, now_utc

SCHEMA = pa.schema(
    [
        ("repo_id", pa.int64()),
        ("full_name", pa.string()),
        ("description", pa.string()),
        ("html_url", pa.string()),
        ("topics", pa.list_(pa.string())),
        ("language", pa.string()),
        ("stars", pa.int64()),
        ("forks", pa.int64()),
        ("created_at", pa.timestamp("us", tz="UTC")),
        ("pushed_at", pa.timestamp("us", tz="UTC")),
        ("search_topic", pa.string()),
        ("collected_at", pa.timestamp("us", tz="UTC")),
    ]
)


def collect() -> list[dict]:
    cfg = config("sources")["github"]
    since = (now_utc() - timedelta(days=cfg["created_within_days"])).date().isoformat()
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    seen: dict[int, dict] = {}
    with http(**headers) as client:
        for topic in cfg["topics"]:
            resp = client.get(
                "https://api.github.com/search/repositories",
                params={
                    "q": f"topic:{topic} created:>={since} stars:>={cfg['min_stars']}",
                    "sort": "stars",
                    "order": "desc",
                    "per_page": cfg["per_topic"],
                },
            )
            if resp.status_code != 200:
                log.warning("github %s: HTTP %s", topic, resp.status_code)
                continue
            for r in resp.json()["items"]:
                seen.setdefault(
                    r["id"],
                    {
                        "repo_id": r["id"],
                        "full_name": r["full_name"],
                        "description": (r.get("description") or "")[:1000],
                        "html_url": r["html_url"],
                        "topics": r.get("topics") or [],
                        "language": r.get("language"),
                        "stars": r["stargazers_count"],
                        "forks": r["forks_count"],
                        "created_at": r["created_at"],
                        "pushed_at": r["pushed_at"],
                        "search_topic": topic,
                        "collected_at": now_utc(),
                    },
                )
    return list(seen.values())
