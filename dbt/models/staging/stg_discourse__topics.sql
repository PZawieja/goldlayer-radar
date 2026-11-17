SELECT
    'discourse:' || forum || ':' || CAST(topic_id AS VARCHAR) AS item_id
    , topic_id
    , {{ snapshot_date() }} AS snapshot_date
    , forum
    , title
    , excerpt
    , url
    , views
    , like_count
    , posts_count
    , created_at AS published_at
    , collected_at
FROM {{ source('raw', 'discourse') }}
