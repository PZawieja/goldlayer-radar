import pyarrow as pa

from radar.common import config, http, log, now_utc

SCHEMA = pa.schema(
    [
        ("topic_id", pa.int64()),
        ("forum", pa.string()),
        ("title", pa.string()),
        ("excerpt", pa.string()),
        ("url", pa.string()),
        ("views", pa.int64()),
        ("like_count", pa.int64()),
        ("posts_count", pa.int64()),
        ("created_at", pa.timestamp("us", tz="UTC")),
        ("collected_at", pa.timestamp("us", tz="UTC")),
    ]
)


def collect() -> list[dict]:
    rows = {}
    with http() as client:
        for forum in config("sources")["discourse"]["forums"]:
            for period in ("daily", "weekly"):
                resp = client.get(f"{forum['url']}/top.json", params={"period": period})
                if resp.status_code != 200:
                    log.warning(
                        "discourse %s: HTTP %s", forum["name"], resp.status_code
                    )
                    continue
                for t in resp.json().get("topic_list", {}).get("topics", []):
                    rows[(forum["name"], t["id"])] = {
                        "topic_id": t["id"],
                        "forum": forum["name"],
                        "title": t.get("title"),
                        "excerpt": (t.get("excerpt") or "")[:500],
                        "url": f"{forum['url']}/t/{t.get('slug')}/{t['id']}",
                        "views": t.get("views") or 0,
                        "like_count": t.get("like_count") or 0,
                        "posts_count": t.get("posts_count") or 0,
                        "created_at": t.get("created_at"),
                        "collected_at": now_utc(),
                    }
    return list(rows.values())
