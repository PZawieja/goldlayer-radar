import os
from datetime import UTC, datetime

import pyarrow as pa

from radar.common import config, data_keywords, http, log, matched_keywords, now_utc

SCHEMA = pa.schema(
    [
        ("post_id", pa.string()),
        ("subreddit", pa.string()),
        ("title", pa.string()),
        ("selftext", pa.string()),
        ("url", pa.string()),
        ("permalink", pa.string()),
        ("score", pa.int64()),
        ("num_comments", pa.int64()),
        ("created_at", pa.timestamp("us", tz="UTC")),
        ("matched_keywords", pa.list_(pa.string())),
        ("collected_at", pa.timestamp("us", tz="UTC")),
    ]
)


def _token() -> str | None:
    cid, secret = (
        os.environ.get("REDDIT_CLIENT_ID"),
        os.environ.get("REDDIT_CLIENT_SECRET"),
    )
    if not (cid and secret):
        return None
    with http() as client:
        resp = client.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(cid, secret),
            data={"grant_type": "client_credentials"},
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


def collect() -> list[dict]:
    cfg = config("sources")["reddit"]
    token = _token()
    base = "https://oauth.reddit.com" if token else "https://www.reddit.com"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    gated = {s.lower() for s in cfg.get("gated_subreddits", [])}
    rows = []
    with http(**headers) as client:
        for sub in cfg["subreddits"]:
            resp = client.get(
                f"{base}/r/{sub}/top.json", params={"t": "day", "limit": cfg["limit"]}
            )
            if resp.status_code != 200:
                log.warning("reddit r/%s: HTTP %s", sub, resp.status_code)
                continue
            for child in resp.json()["data"]["children"]:
                p = child["data"]
                if p.get("score", 0) < cfg["min_score"] or p.get("stickied"):
                    continue
                text = f"{p.get('title', '')} {p.get('selftext', '')[:500]}"
                if sub.lower() in gated and not data_keywords(text):
                    continue
                kws = matched_keywords(text)
                rows.append(
                    {
                        "post_id": p["id"],
                        "subreddit": sub,
                        "title": p.get("title"),
                        "selftext": (p.get("selftext") or "")[:500],
                        "url": p.get("url"),
                        "permalink": f"https://www.reddit.com{p.get('permalink')}",
                        "score": p.get("score") or 0,
                        "num_comments": p.get("num_comments") or 0,
                        "created_at": datetime.fromtimestamp(p["created_utc"], UTC),
                        "matched_keywords": kws,
                        "collected_at": now_utc(),
                    }
                )
    return rows
