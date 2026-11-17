WITH weekly AS (
    SELECT
        cur.*
        , COALESCE(prev.engagement_score, 0) AS prev_engagement_score
        , (cur.engagement_score - COALESCE(prev.engagement_score, 0))
        / (COALESCE(prev.engagement_score, 0) + 1) AS growth
    FROM {{ ref('int_topic_weekly_activity') }} AS cur
    LEFT JOIN {{ ref('int_topic_weekly_activity') }} AS prev
        ON
            cur.cluster_key = prev.cluster_key
            AND prev.week_start = cur.week_start - INTERVAL 7 DAY
)

SELECT
    cluster_week_id
    , cluster_key
    , cluster_label
    , week_start
    , category
    , primary_tag
    , item_type
    , items
    , distinct_sources
    , has_primary_source
    , engagement_score
    , prev_engagement_score
    , growth
    , ROUND(
        0.6 * PERCENT_RANK() OVER (PARTITION BY week_start ORDER BY engagement_score)
        + 0.4 * PERCENT_RANK() OVER (PARTITION BY week_start ORDER BY growth)
        , 3
    ) AS momentum_norm
    , ROUND(LEAST(distinct_sources / 4.0, 1.0), 3) AS spread_norm
FROM weekly
