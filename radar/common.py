import logging
import re
from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"
USER_AGENT = "goldlayer-radar/0.1 (trend research bot)"

log = logging.getLogger("radar")


@cache
def config(name: str) -> dict:
    return yaml.safe_load((CONFIG / f"{name}.yml").read_text())


def http(**headers: str) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, **headers}, timeout=30, follow_redirects=True
    )


@cache
def _pattern(kind: str) -> re.Pattern:
    words = sorted(config("sources")[kind], key=len, reverse=True)
    alt = "|".join(re.escape(w) for w in words)
    return re.compile(r"\b(" + alt + r")\b", re.IGNORECASE)


def data_keywords(text: str) -> list[str]:
    return sorted({m.lower() for m in _pattern("data_keywords").findall(text or "")})


def matched_keywords(text: str) -> list[str]:
    ai = {m.lower() for m in _pattern("ai_keywords").findall(text or "")}
    return sorted(set(data_keywords(text)) | ai)


def now_utc() -> datetime:
    return datetime.now(UTC)


def parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def write_parquet(rows: list[dict], schema: pa.Schema, source: str, run_date: date):
    out = DATA / "raw" / run_date.isoformat() / f"{source}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    ts_cols = [f.name for f in schema if pa.types.is_timestamp(f.type)]
    for row in rows:
        for col in ts_cols:
            if isinstance(row.get(col), str):
                row[col] = parse_ts(row[col])
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, out)
    log.info("%s: %d rows -> %s", source, len(rows), out.relative_to(ROOT))
    return out
