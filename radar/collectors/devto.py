import time

import pyarrow as pa

from radar.common import config, data_keywords, http, log, matched_keywords, now_utc

SCHEMA = pa.schema(
    [
        ("article_id", pa.int64()),
        ("title", pa.string()),
        ("description", pa.string()),
        ("url", pa.string()),
        ("tags", pa.list_(pa.string())),
        ("reactions", pa.int64()),
        ("comments", pa.int64()),
        ("published_at", pa.timestamp("us", tz="UTC")),
        ("matched_keywords", pa.list_(pa.string())),
        ("collected_at", pa.timestamp("us", tz="UTC")),
    ]
)


def _get(client, tag: str, cfg: dict):
    params = {"tag": tag, "top": cfg["top_days"], "per_page": cfg["per_tag"]}
    for attempt in range(3):
        resp = client.get("https://dev.to/api/articles", params=params)
        if resp.status_code != 429:
            return resp
        time.sleep(5 * (attempt + 1))
    return resp


def collect() -> list[dict]:
    cfg = config("sources")["devto"]
    rows = {}
    with http() as client:
        for tag in cfg["tags"]:
            resp = _get(client, tag, cfg)
            time.sleep(1.5)
            if resp.status_code != 200:
                log.warning("devto #%s: HTTP %s", tag, resp.status_code)
                continue
            for a in resp.json():
                if (a.get("positive_reactions_count") or 0) < cfg["min_reactions"]:
                    continue
                tags = a.get("tag_list") or []
                text = (
                    f"{a.get('title', '')} {a.get('description', '')} {' '.join(tags)}"
                )
                if not data_keywords(text):
                    continue
                rows[a["id"]] = {
                    "article_id": a["id"],
                    "title": a.get("title"),
                    "description": (a.get("description") or "")[:500],
                    "url": a.get("url"),
                    "tags": tags,
                    "reactions": a.get("positive_reactions_count") or 0,
                    "comments": a.get("comments_count") or 0,
                    "published_at": a.get("published_at"),
                    "matched_keywords": matched_keywords(text),
                    "collected_at": now_utc(),
                }
    return list(rows.values())
