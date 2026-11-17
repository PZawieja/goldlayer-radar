SELECT
    item_id
    , is_relevant
    , category
    , primary_tag
    , item_type
    , source_kind
    , topic_key
    , model
    , classified_at
FROM {{ source('llm', 'classified_items') }}
QUALIFY ROW_NUMBER() OVER (PARTITION BY item_id ORDER BY classified_at DESC) = 1
