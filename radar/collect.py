import argparse
import logging
from datetime import date
from importlib import import_module

import httpx

from radar.common import log, write_parquet

SOURCES = [
    "hn",
    "reddit",
    "github",
    "pypi",
    "hf_papers",
    "bluesky",
    "rss",
    "discourse",
    "devto",
    "lobsters",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--only", nargs="*", choices=SOURCES)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    failed = []
    for name in args.only or SOURCES:
        mod = import_module(f"radar.collectors.{name}")
        try:
            rows = mod.collect()
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            log.exception("%s collector failed", name)
            failed.append(name)
            rows = []
        write_parquet(rows, mod.SCHEMA, name, args.date)
    if len(failed) == len(args.only or SOURCES):
        raise SystemExit("all collectors failed")


if __name__ == "__main__":
    main()
