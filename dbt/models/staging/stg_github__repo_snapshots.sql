SELECT
    'github:' || CAST(repo_id AS VARCHAR) AS item_id
    , repo_id
    , {{ snapshot_date() }} AS snapshot_date
    , full_name
    , description
    , html_url
    , topics
    , language
    , stars
    , forks
    , created_at
    , pushed_at
    , search_topic
    , collected_at
FROM {{ source('raw', 'github') }}
