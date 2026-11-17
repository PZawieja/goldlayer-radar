import pyarrow as pa

from radar.common import config, http, log, now_utc

SCHEMA = pa.schema(
    [
        ("package", pa.string()),
        ("last_day", pa.int64()),
        ("last_week", pa.int64()),
        ("last_month", pa.int64()),
        ("collected_at", pa.timestamp("us", tz="UTC")),
    ]
)


def collect() -> list[dict]:
    rows = []
    with http() as client:
        for pkg in config("sources")["pypi"]["packages"]:
            resp = client.get(f"https://pypistats.org/api/packages/{pkg}/recent")
            if resp.status_code != 200:
                log.warning("pypi %s: HTTP %s", pkg, resp.status_code)
                continue
            d = resp.json()["data"]
            rows.append({"package": pkg, **d, "collected_at": now_utc()})
    return rows
