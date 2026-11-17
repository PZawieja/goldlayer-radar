import argparse
import json
import logging
import re
import time
from datetime import date

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

from radar.common import DATA, config, log, now_utc, write_parquet
from radar.llm import (
    CLASSIFIED_SCHEMA,
    CLASSIFY_MODEL,
    Classification,
    client,
    db,
    first_text,
    json_schema,
)

PENDING = DATA / "classified" / "pending_batch.json"
LOOKBACK_DAYS = 8


def _system() -> str:
    cats = "\n".join(
        f"- {k}: {v['label']} (site tag: {v['tag']})"
        for k, v in config("taxonomy")["categories"].items()
    )
    return (
        "You classify items for the trend radar of goldlayer.dev, a practical blog "
        "for analytics engineers. Its lane: dbt best practices, incremental "
        "models and large projects, SQL, Snowflake/BigQuery features and cost, "
        "CI/CD and git for data teams, self-healing pipelines and alerting, data "
        "quality, semantic layers, AE tools and setups (IDE, LLMs in VS Code), "
        "data team structure and AE skills, and AI built by data teams "
        "(analytics agents, context, model choice and AI cost, evals, Slack/Teams "
        "data bots, LLMs for pipeline development, real company use cases).\n\n"
        f"Categories:\n{cats}\n\n"
        "is_relevant=true ONLY if an analytics engineer could apply it in their "
        "warehouse, dbt project, SQL, BI layer, data tests, or an AI agent working "
        "on their data. Mark is_relevant=false for: general model releases and "
        "benchmarks, coding agents or MCP servers unrelated to data, consumer AI, "
        "ML research without a data-stack application, career/opinion posts with "
        "no concrete practice or lesson, spam or star-farmed repos, and homonyms (e.g. DBT = "
        "dialectical behavior therapy). Irrelevant items use category 'other' and "
        "primary_tag 'none'. primary_tag follows the category's site tag unless "
        "the item clearly fits another (e.g. Snowflake Cortex -> Snowflake). Reuse "
        "common topic_key wording so similar items share a key."
    )


def pending_items(limit: int | None) -> list[dict]:
    sql = f"""
        SELECT i.item_id, i.source, i.title, LEFT(COALESCE(i.body, ''), 600) AS body,
               i.url, i.engagement
        FROM int_items AS i
        LEFT JOIN stg_llm__classified_items AS c USING (item_id)
        WHERE c.item_id IS NULL
          AND i.last_seen_date >= CURRENT_DATE - INTERVAL {LOOKBACK_DAYS} DAY
        ORDER BY i.engagement_pct DESC
    """
    rows = db().sql(sql).fetchall()
    cols = ["item_id", "source", "title", "body", "url", "engagement"]
    items = [dict(zip(cols, r, strict=True)) for r in rows]
    return items[:limit] if limit else items


def _params(item: dict) -> MessageCreateParamsNonStreaming:
    content = (
        f"source: {item['source']}\nurl: {item['url']}\ntitle: {item['title']}\n"
        f"engagement: {item['engagement']}\ntext: {item['body']}"
    )
    return MessageCreateParamsNonStreaming(
        model=CLASSIFY_MODEL,
        max_tokens=2048,
        system=[
            {"type": "text", "text": _system(), "cache_control": {"type": "ephemeral"}}
        ],
        messages=[{"role": "user", "content": content}],
        output_config={"effort": "low", "format": json_schema(Classification)},
    )


def _custom_id(n: int) -> str:
    return f"item-{n}"


def submit(items: list[dict]) -> str:
    batch = client().messages.batches.create(
        requests=[
            Request(custom_id=_custom_id(n), params=_params(it))
            for n, it in enumerate(items)
        ]
    )
    PENDING.write_text(
        json.dumps({"batch_id": batch.id, "item_ids": [i["item_id"] for i in items]})
    )
    log.info("submitted batch %s with %d items", batch.id, len(items))
    return batch.id


def collect_results(timeout_s: int) -> int:
    pending = json.loads(PENDING.read_text())
    c = client()
    deadline = time.time() + timeout_s
    while (
        b := c.messages.batches.retrieve(pending["batch_id"])
    ).processing_status != "ended":
        if time.time() > deadline:
            log.warning(
                "batch %s still %s; will resume next run", b.id, b.processing_status
            )
            return 0
        time.sleep(30)
    rows = []
    errors = 0
    for res in c.messages.batches.results(pending["batch_id"]):
        n = int(res.custom_id.removeprefix("item-"))
        if res.result.type != "succeeded":
            errors += 1
            continue
        try:
            parsed = Classification.model_validate_json(first_text(res.result.message))
        except (ValueError, StopIteration):
            errors += 1
            continue
        rows.append(_row(pending["item_ids"][n], parsed))
    _write(rows)
    PENDING.unlink()
    log.info("classified %d items (%d errors)", len(rows), errors)
    return len(rows)


def _row(item_id: str, c: Classification) -> dict:
    return {
        "item_id": item_id,
        **c.model_dump(),
        "topic_key": re.sub(r"[^a-z0-9-]+", "-", c.topic_key.lower()).strip("-"),
        "model": CLASSIFY_MODEL,
        "classified_at": now_utc(),
    }


def _write(rows: list[dict]):
    if not rows:
        return
    stamp = now_utc().strftime("%Y-%m-%dT%H%M%S")
    write_parquet(rows, CLASSIFIED_SCHEMA, f"items_{stamp}", date.today())
    src = DATA / "raw" / date.today().isoformat() / f"items_{stamp}.parquet"
    src.rename(DATA / "classified" / src.name)


def run_sync(items: list[dict]):
    rows = []
    c = client()
    for it in items:
        try:
            msg = c.messages.create(**_params(it))
            rows.append(
                _row(it["item_id"], Classification.model_validate_json(first_text(msg)))
            )
        except (anthropic.APIError, ValueError, StopIteration) as exc:
            log.warning("%s: %s", it["item_id"], exc)
    _write(rows)
    log.info("classified %d/%d items", len(rows), len(items))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--sync", action="store_true", help="no batch; for small tests")
    p.add_argument("--timeout", type=int, default=7200)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if PENDING.exists() and not args.dry_run:
        collect_results(args.timeout)
        return
    items = pending_items(args.limit)
    log.info("%d items to classify", len(items))
    if args.dry_run:
        print(_system(), "\n---")
        for it in items[:5]:
            print(_params(it)["messages"][0]["content"], "\n---")
        print(json.dumps(json_schema(Classification), indent=2))
        return
    if not items:
        return
    if args.sync:
        run_sync(items)
    else:
        submit(items)
        collect_results(args.timeout)


if __name__ == "__main__":
    main()
