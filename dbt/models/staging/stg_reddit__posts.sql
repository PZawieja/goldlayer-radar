SELECT
    'reddit:' || post_id AS item_id
    , post_id
    , {{ snapshot_date() }} AS snapshot_date
    , subreddit
    , title
    , selftext
    , url
    , permalink
    , score
    , num_comments
    , created_at AS published_at
    , matched_keywords
    , collected_at
FROM {{ source('raw', 'reddit') }}
