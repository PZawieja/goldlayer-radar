SELECT
    'hn:' || object_id AS item_id
    , object_id
    , {{ snapshot_date() }} AS snapshot_date
    , title
    , url
    , author
    , points
    , num_comments
    , created_at AS published_at
    , matched_keywords
    , collected_at
FROM {{ source('raw', 'hn') }}
