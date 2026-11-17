SELECT
    i.item_id
    , i.source
    , i.title
    , i.body
    , i.url
    , COALESCE(c.source_kind, i.source_kind) AS source_kind
    , i.published_at
    , i.matched_keywords
    , i.engagement
    , i.comments
    , i.engagement_per_day
    , i.engagement_pct
    , i.first_seen_date
    , i.last_seen_date
    , i.snapshots
    , c.item_id IS NOT NULL AS is_classified
    , COALESCE(c.is_relevant, FALSE) AS is_relevant
    , c.category
    , c.primary_tag
    , c.item_type
    , c.topic_key
FROM {{ ref('int_items') }} AS i
LEFT JOIN {{ ref('stg_llm__classified_items') }} AS c ON i.item_id = c.item_id
