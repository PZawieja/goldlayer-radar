import pyarrow as pa

from radar.common import config, http, log, now_utc

SCHEMA = pa.schema(
    [
        ("paper_id", pa.string()),
        ("title", pa.string()),
        ("summary", pa.string()),
        ("upvotes", pa.int64()),
        ("num_comments", pa.int64()),
        ("published_at", pa.timestamp("us", tz="UTC")),
        ("collected_at", pa.timestamp("us", tz="UTC")),
    ]
)


def collect() -> list[dict]:
    cfg = config("sources")["hf_papers"]
    with http() as client:
        resp = client.get(
            "https://huggingface.co/api/daily_papers", params={"limit": cfg["limit"]}
        )
    if resp.status_code != 200:
        log.warning("hf_papers: HTTP %s", resp.status_code)
        return []
    rows = []
    for item in resp.json():
        p = item.get("paper", item)
        upvotes = p.get("upvotes") or 0
        if upvotes < cfg["min_upvotes"]:
            continue
        rows.append(
            {
                "paper_id": p["id"],
                "title": p.get("title") or item.get("title"),
                "summary": (p.get("summary") or "")[:2000],
                "upvotes": upvotes,
                "num_comments": item.get("numComments") or 0,
                "published_at": p.get("publishedAt") or item.get("publishedAt"),
                "collected_at": now_utc(),
            }
        )
    return rows
