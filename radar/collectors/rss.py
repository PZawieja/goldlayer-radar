import calendar
import hashlib
import html
import re
from datetime import UTC, datetime, timedelta

import feedparser
import httpx
import pyarrow as pa

from radar.common import config, http, log, matched_keywords, now_utc

SCHEMA = pa.schema(
    [
        ("entry_id", pa.string()),
        ("feed_name", pa.string()),
        ("source_kind", pa.string()),
        ("title", pa.string()),
        ("summary", pa.string()),
        ("url", pa.string()),
        ("published_at", pa.timestamp("us", tz="UTC")),
        ("matched_keywords", pa.list_(pa.string())),
        ("collected_at", pa.timestamp("us", tz="UTC")),
    ]
)

LOOKBACK = timedelta(days=3)


def _published(entry) -> datetime | None:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime.fromtimestamp(calendar.timegm(t), UTC) if t else None


def collect() -> list[dict]:
    cutoff = now_utc() - LOOKBACK
    rows = []
    with http() as client:
        for feed in config("sources")["rss"]:
            try:
                resp = client.get(feed["url"])
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                log.warning("rss %s: %s", feed["name"], exc)
                continue
            parsed = feedparser.parse(resp.content)
            for e in parsed.entries:
                published = _published(e)
                if published and published < cutoff:
                    continue
                link = e.get("link", "")
                raw = re.sub(r"<[^>]+>", " ", e.get("summary") or "")
                summary = re.sub(r"\s+", " ", html.unescape(raw)).strip()[:2000]
                rows.append(
                    {
                        "entry_id": hashlib.sha1(link.encode()).hexdigest(),
                        "feed_name": feed["name"],
                        "source_kind": feed["kind"],
                        "title": e.get("title"),
                        "summary": summary,
                        "url": link,
                        "published_at": published,
                        "matched_keywords": matched_keywords(
                            f"{e.get('title', '')} {summary}"
                        ),
                        "collected_at": now_utc(),
                    }
                )
    return rows
