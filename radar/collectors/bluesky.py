import pyarrow as pa

from radar.common import config, http, log, matched_keywords, now_utc

SCHEMA = pa.schema(
    [
        ("uri", pa.string()),
        ("author_handle", pa.string()),
        ("text", pa.string()),
        ("url", pa.string()),
        ("like_count", pa.int64()),
        ("repost_count", pa.int64()),
        ("reply_count", pa.int64()),
        ("created_at", pa.timestamp("us", tz="UTC")),
        ("query", pa.string()),
        ("matched_keywords", pa.list_(pa.string())),
        ("collected_at", pa.timestamp("us", tz="UTC")),
    ]
)


def collect() -> list[dict]:
    cfg = config("sources")["bluesky"]
    seen: dict[str, dict] = {}
    with http() as client:
        for q in cfg["queries"]:
            resp = client.get(
                "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts",
                params={"q": q, "sort": "top", "limit": cfg["limit"]},
            )
            if resp.status_code != 200:
                log.warning(
                    "bluesky %s: HTTP %s (skipping source)", q, resp.status_code
                )
                return list(seen.values())
            for post in resp.json().get("posts", []):
                if (post.get("likeCount") or 0) < cfg["min_likes"]:
                    continue
                rec = post["record"]
                handle = post["author"]["handle"]
                rkey = post["uri"].rsplit("/", 1)[-1]
                seen[post["uri"]] = {
                    "uri": post["uri"],
                    "author_handle": handle,
                    "text": rec.get("text", "")[:300],
                    "url": f"https://bsky.app/profile/{handle}/post/{rkey}",
                    "like_count": post.get("likeCount") or 0,
                    "repost_count": post.get("repostCount") or 0,
                    "reply_count": post.get("replyCount") or 0,
                    "created_at": rec.get("createdAt"),
                    "query": q,
                    "matched_keywords": matched_keywords(rec.get("text", "")),
                    "collected_at": now_utc(),
                }
    return list(seen.values())
