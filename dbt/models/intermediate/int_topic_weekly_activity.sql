WITH items AS (
    SELECT
        i.item_id
        , i.source
        , i.engagement_pct
        , COALESCE(lc.source_kind, i.source_kind) AS source_kind
        , lc.category
        , lc.primary_tag
        , lc.item_type
        , tc.cluster_key
        , tc.cluster_label
        , CAST(DATE_TRUNC('week', i.first_seen_date) AS DATE) AS week_start
    FROM {{ ref('int_items') }} AS i
    INNER JOIN {{ ref('stg_llm__classified_items') }} AS lc ON i.item_id = lc.item_id
    INNER JOIN {{ ref('stg_llm__topic_clusters') }} AS tc
        ON lc.topic_key = tc.topic_key
    WHERE lc.is_relevant
)

SELECT
    cluster_key || ':' || CAST(week_start AS VARCHAR) AS cluster_week_id
    , cluster_key
    , ANY_VALUE(cluster_label) AS cluster_label
    , week_start
    , COUNT(*) AS items
    , COUNT(DISTINCT source) AS distinct_sources
    , SUM(engagement_pct) AS engagement_score
    , BOOL_OR(source_kind = 'primary') AS has_primary_source
    , MODE(category) AS category
    , MODE(primary_tag) AS primary_tag
    , MODE(item_type) AS item_type
FROM items
GROUP BY cluster_key, week_start
