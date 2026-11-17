import argparse
import logging

import pyarrow as pa
import pyarrow.parquet as pq

from radar.common import DATA, log, now_utc
from radar.llm import CLUSTER_SCHEMA, ClusterResult, call_structured, db

CLUSTERS = DATA / "classified" / "clusters.parquet"

SYSTEM = (
    "You maintain topic clusters for a data/AI trend radar. Each new topic_key must "
    "map to an existing cluster when it is the same underlying topic (same tool, "
    "release, technique or debate), otherwise to a new cluster. Clusters should be "
    "specific enough to write one blog post about ('dbt-fusion-engine', not 'dbt'). "
    "Return exactly one assignment per new topic_key, copying the key verbatim."
)


def unmapped_topic_keys() -> list[tuple[str, int]]:
    return (
        db()
        .sql("""
        SELECT c.topic_key, COUNT(*) AS n
        FROM stg_llm__classified_items AS c
        LEFT JOIN stg_llm__topic_clusters AS t USING (topic_key)
        WHERE c.is_relevant AND t.topic_key IS NULL
        GROUP BY 1
        ORDER BY 2 DESC
    """)
        .fetchall()
    )


def existing_clusters() -> list[tuple[str, str]]:
    return (
        db()
        .sql("""
        SELECT cluster_key, ANY_VALUE(cluster_label)
        FROM stg_llm__topic_clusters
        WHERE clustered_at >= CURRENT_DATE - INTERVAL 60 DAY
        GROUP BY 1
    """)
        .fetchall()
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    new = unmapped_topic_keys()
    if not new:
        log.info("no new topic keys")
        return
    clusters = existing_clusters()
    user = (
        "Existing clusters (key | label):\n"
        + ("\n".join(f"{k} | {lbl}" for k, lbl in clusters) or "(none yet)")
        + "\n\nNew topic_keys (key | item count):\n"
        + "\n".join(f"{k} | {n}" for k, n in new)
    )
    if args.dry_run:
        print(user)
        return
    result, usage = call_structured(
        ClusterResult, [{"type": "text", "text": SYSTEM}], user, effort="medium"
    )
    wanted = {k for k, _ in new}
    rows = [
        {**a.model_dump(), "clustered_at": now_utc()}
        for a in result.assignments
        if a.topic_key in wanted
    ]
    missing = wanted - {r["topic_key"] for r in rows}
    rows += [
        {
            "topic_key": k,
            "cluster_key": k,
            "cluster_label": k.replace("-", " "),
            "clustered_at": now_utc(),
        }
        for k in missing
    ]
    old = pq.read_table(CLUSTERS, schema=CLUSTER_SCHEMA).to_pylist()
    seen = set()
    merged = []
    for r in old + rows:
        if r["topic_key"] not in seen:
            seen.add(r["topic_key"])
            merged.append(r)

    pq.write_table(pa.Table.from_pylist(merged, schema=CLUSTER_SCHEMA), CLUSTERS)
    log.info(
        "mapped %d new topic keys (%d fallback); tokens in=%s out=%s",
        len(rows),
        len(missing),
        usage.input_tokens,
        usage.output_tokens,
    )


if __name__ == "__main__":
    main()
