SELECT
    'rss:' || entry_id AS item_id
    , entry_id
    , {{ snapshot_date() }} AS snapshot_date
    , feed_name
    , source_kind
    , title
    , summary
    , url
    , published_at
    , matched_keywords
    , collected_at
FROM {{ source('raw', 'rss') }}
