WITH ranked AS (
    SELECT
        *
        , ROW_NUMBER() OVER (
            PARTITION BY item_id ORDER BY snapshot_date DESC
        ) AS rn_latest
    FROM {{ ref('int_item_snapshots') }}
)

, agg AS (
    SELECT
        item_id
        , MIN(snapshot_date) AS first_seen_date
        , MAX(snapshot_date) AS last_seen_date
        , COUNT(*) AS snapshots
        , MAX(engagement) - MIN(engagement) AS engagement_gain
        , DATE_DIFF('day', MIN(snapshot_date), MAX(snapshot_date)) AS observed_days
    FROM ranked
    GROUP BY item_id
)

SELECT
    r.item_id
    , r.source
    , r.title
    , r.body
    , r.url
    , r.source_kind
    , r.published_at
    , r.matched_keywords
    , r.engagement
    , r.comments
    , a.first_seen_date
    , a.last_seen_date
    , a.snapshots
    , CASE
        WHEN a.observed_days > 0 THEN a.engagement_gain / a.observed_days
        WHEN r.source = 'github'
            THEN r.engagement / GREATEST(
                DATE_DIFF('day', CAST(r.published_at AS DATE), a.last_seen_date), 1
            )
        ELSE r.engagement
    END AS engagement_per_day
    , CASE
        WHEN r.engagement IS NULL THEN 0.5
        ELSE PERCENT_RANK() OVER (
            PARTITION BY r.source, DATE_TRUNC('week', a.first_seen_date)
            ORDER BY r.engagement
        )
    END AS engagement_pct
FROM ranked AS r
INNER JOIN agg AS a ON r.item_id = a.item_id
WHERE r.rn_latest = 1
