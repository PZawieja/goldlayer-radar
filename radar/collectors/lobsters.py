import pyarrow as pa

from radar.common import config, data_keywords, http, log, matched_keywords, now_utc

SCHEMA = pa.schema(
    [
        ("short_id", pa.string()),
        ("title", pa.string()),
        ("url", pa.string()),
        ("comments_url", pa.string()),
        ("tags", pa.list_(pa.string())),
        ("score", pa.int64()),
        ("comment_count", pa.int64()),
        ("created_at", pa.timestamp("us", tz="UTC")),
        ("matched_keywords", pa.list_(pa.string())),
        ("collected_at", pa.timestamp("us", tz="UTC")),
    ]
)


def collect() -> list[dict]:
    cfg = config("sources")["lobsters"]
    rows = {}
    with http() as client:
        for tag in cfg["tags"]:
            resp = client.get(f"https://lobste.rs/t/{tag}.json")
            if resp.status_code != 200:
                log.warning("lobsters %s: HTTP %s", tag, resp.status_code)
                continue
            for s in resp.json():
                if (s.get("score") or 0) < cfg["min_score"]:
                    continue
                if not data_keywords(s.get("title", "")):
                    continue
                rows[s["short_id"]] = {
                    "short_id": s["short_id"],
                    "title": s.get("title"),
                    "url": s.get("url") or s.get("comments_url"),
                    "comments_url": s.get("comments_url"),
                    "tags": s.get("tags") or [],
                    "score": s.get("score") or 0,
                    "comment_count": s.get("comment_count") or 0,
                    "created_at": s.get("created_at"),
                    "matched_keywords": matched_keywords(s.get("title", "")),
                    "collected_at": now_utc(),
                }
    return list(rows.values())
