from datetime import timedelta

import pyarrow as pa

from radar.common import config, http, log, matched_keywords, now_utc

SCHEMA = pa.schema(
    [
        ("object_id", pa.string()),
        ("title", pa.string()),
        ("url", pa.string()),
        ("author", pa.string()),
        ("points", pa.int64()),
        ("num_comments", pa.int64()),
        ("created_at", pa.timestamp("us", tz="UTC")),
        ("matched_keywords", pa.list_(pa.string())),
        ("collected_at", pa.timestamp("us", tz="UTC")),
    ]
)


def collect() -> list[dict]:
    cfg = config("sources")["hn"]
    since = int((now_utc() - timedelta(hours=cfg["lookback_hours"])).timestamp())
    seen: dict[str, dict] = {}
    with http() as client:
        for kw in config("sources")["keywords"]:
            resp = client.get(
                "https://hn.algolia.com/api/v1/search_by_date",
                params={
                    "query": kw,
                    "tags": "story",
                    "numericFilters": f"created_at_i>{since},points>={cfg['min_points']}",
                    "hitsPerPage": cfg["hits_per_query"],
                },
            )
            if resp.status_code != 200:
                log.warning("hn %s: HTTP %s", kw, resp.status_code)
                continue
            for hit in resp.json()["hits"]:
                kws = matched_keywords(hit.get("title", ""))
                if not kws:
                    continue
                seen[hit["objectID"]] = {
                    "object_id": hit["objectID"],
                    "title": hit.get("title"),
                    "url": hit.get("url")
                    or f"https://news.ycombinator.com/item?id={hit['objectID']}",
                    "author": hit.get("author"),
                    "points": hit.get("points") or 0,
                    "num_comments": hit.get("num_comments") or 0,
                    "created_at": hit["created_at"],
                    "matched_keywords": kws,
                    "collected_at": now_utc(),
                }
    return list(seen.values())
