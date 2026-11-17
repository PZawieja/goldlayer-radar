SELECT
    'devto:' || CAST(article_id AS VARCHAR) AS item_id
    , article_id
    , {{ snapshot_date() }} AS snapshot_date
    , title
    , description
    , url
    , tags
    , reactions
    , comments
    , published_at
    , matched_keywords
    , collected_at
FROM {{ source('raw', 'devto') }}
