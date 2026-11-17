import argparse
import json
import logging
import os
from pathlib import Path

from notion_client import Client

from radar.common import config, log

STATUSES = ["New", "Shortlisted", "Writing", "Published", "Skipped"]
SELECTS = {
    "Verdict": ["Write now", "Watch", "Skip", "Breaking"],
    "Status": STATUSES,
    "Primary tag": [*config("taxonomy")["site_tags"], "new-tag-candidate", "none"],
    "Category": [v["label"] for v in config("taxonomy")["categories"].values()],
    "Type": config("taxonomy")["item_types"],
    "Format": ["tutorial", "build log", "comparison", "opinion", "explainer"],
}
TEXTS = [
    "Topic Key",
    "Why it matters",
    "Intended reader",
    "Reader outcome",
    "Post angle",
    "Example scenario",
    "Suggested titles",
    "LinkedIn hook",
    "Covered by",
    "Primary sources",
    "Other evidence",
]
NUMBERS = ["Score", "Momentum", "Sources", "Items"]
DATES = ["Week", "Checked on"]


def opt(name: str) -> str:
    return name.replace(",", " /")[:100]


def schema() -> dict:
    props = {"Topic": {"title": {}}}
    props |= {
        k: {"select": {"options": [{"name": opt(n)} for n in v]}}
        for k, v in SELECTS.items()
    }
    props |= {k: {"rich_text": {}} for k in TEXTS}
    props |= {k: {"number": {}} for k in NUMBERS}
    props |= {k: {"date": {}} for k in DATES}
    props["Breaking"] = {"checkbox": {}}
    return props


def notion() -> Client:
    return Client(auth=os.environ["NOTION_TOKEN"])


def text(value: str) -> dict:
    chunks = [value[i : i + 1900] for i in range(0, min(len(value), 5700), 1900)]
    return {"rich_text": [{"type": "text", "text": {"content": c}} for c in chunks]}


def links(urls: list[str]) -> dict:
    return {
        "rich_text": [
            {"type": "text", "text": {"content": u + "\n", "link": {"url": u}}}
            for u in urls[:20]
        ]
    }


def setup(parent_page_id: str):
    db = notion().databases.create(
        parent={"type": "page_id", "page_id": parent_page_id},
        title=[{"type": "text", "text": {"content": "Trend Radar"}}],
        initial_data_source={"properties": schema()},
    )
    print("database_id:", db["id"])
    print("NOTION_DATA_SOURCE_ID:", db["data_sources"][0]["id"])


def existing_pages(client: Client, ds_id: str) -> dict[str, dict]:
    pages, cursor = {}, None
    while True:
        kwargs = {"page_size": 100, **({"start_cursor": cursor} if cursor else {})}
        resp = client.data_sources.query(ds_id, **kwargs)
        for p in resp["results"]:
            key = "".join(
                t["plain_text"] for t in p["properties"]["Topic Key"]["rich_text"]
            )
            status = (p["properties"]["Status"]["select"] or {}).get("name")
            pages[key] = {"id": p["id"], "status": status}
        if not resp.get("has_more"):
            return pages
        cursor = resp["next_cursor"]


def properties(r: dict) -> dict:
    cat_labels = config("taxonomy")["categories"]
    props = {
        "Topic": {"title": [{"text": {"content": r["cluster_label"][:200]}}]},
        "Topic Key": text(r["cluster_key"]),
        "Score": {"number": r["score"]},
        "Verdict": {"select": {"name": opt(r["verdict"])}},
        "Primary tag": {"select": {"name": opt(r["primary_tag"] or "none")}},
        "Category": {
            "select": {
                "name": cat_labels.get(r["category"], {}).get(
                    "label", "Other / off-topic"
                )
            }
        },
        "Type": {"select": {"name": opt(r["item_type"])}}
        if r.get("item_type")
        else {"select": None},
        "Momentum": {"number": r.get("momentum_norm")},
        "Sources": {"number": r.get("distinct_sources")},
        "Items": {"number": r.get("items")},
        "Week": {"date": {"start": r["week_start"]}},
        "Checked on": {"date": {"start": r["checked_on"]}},
        "Breaking": {"checkbox": bool(r.get("breaking"))},
        "Primary sources": links(r.get("primary_sources", [])),
        "Other evidence": links(r.get("other_evidence", [])),
    }
    optional = {
        "Why it matters": "why_it_matters",
        "Intended reader": "intended_reader",
        "Reader outcome": "reader_outcome",
        "Post angle": "post_angle",
        "Example scenario": "example_scenario",
        "LinkedIn hook": "linkedin_hook",
        "Covered by": "covered_by",
    }
    for prop, key in optional.items():
        if r.get(key):
            props[prop] = text(r[key])
    if r.get("titles"):
        props["Suggested titles"] = text("\n".join(r["titles"]))
    if r.get("post_format"):
        props["Format"] = {"select": {"name": opt(r["post_format"])}}
    return props


def sync(rows: list[dict]) -> tuple[int, int]:
    client = notion()
    ds_id = os.environ["NOTION_DATA_SOURCE_ID"]
    pages = existing_pages(client, ds_id)
    penalty = config("scoring")["covered_penalty"]
    created = updated = 0
    for r in rows:
        page = pages.get(r["cluster_key"])
        if page and page["status"] in ("Published", "Skipped"):
            r = {**r, "score": round(r["score"] * penalty, 1)}
        props = properties(r)
        if page:
            client.pages.update(page["id"], properties=props)
            updated += 1
        else:
            props["Status"] = {"select": {"name": "New"}}
            client.pages.create(
                parent={"type": "data_source_id", "data_source_id": ds_id},
                properties=props,
            )
            created += 1
    return created, updated


def main():
    p = argparse.ArgumentParser()
    p.add_argument("scored_file", nargs="?", type=Path)
    p.add_argument("--setup", metavar="PARENT_PAGE_ID")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if args.setup:
        setup(args.setup)
        return
    rows = json.loads(args.scored_file.read_text())
    created, updated = sync(rows)
    log.info("notion: %d created, %d updated", created, updated)


if __name__ == "__main__":
    main()
