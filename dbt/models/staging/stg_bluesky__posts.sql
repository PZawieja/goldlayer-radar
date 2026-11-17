SELECT
    'bsky:' || uri AS item_id
    , uri
    , {{ snapshot_date() }} AS snapshot_date
    , author_handle
    , text
    , url
    , like_count
    , repost_count
    , reply_count
    , created_at AS published_at
    , query
    , matched_keywords
    , collected_at
FROM {{ source('raw', 'bluesky') }}
