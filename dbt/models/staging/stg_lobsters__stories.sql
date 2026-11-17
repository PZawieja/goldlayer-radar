SELECT
    'lobsters:' || short_id AS item_id
    , short_id
    , {{ snapshot_date() }} AS snapshot_date
    , title
    , url
    , comments_url
    , tags
    , score
    , comment_count
    , created_at AS published_at
    , matched_keywords
    , collected_at
FROM {{ source('raw', 'lobsters') }}
