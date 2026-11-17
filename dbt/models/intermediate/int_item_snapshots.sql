WITH unioned AS (
    SELECT
        item_id
        , 'hn' AS source
        , snapshot_date
        , title
        , NULL AS body
        , url
        , 'secondary' AS source_kind
        , points AS engagement
        , num_comments AS comments
        , published_at
        , matched_keywords
    FROM {{ ref('stg_hn__items') }}

    UNION ALL

    SELECT
        item_id
        , 'reddit' AS source
        , snapshot_date
        , title
        , selftext AS body
        , permalink AS url
        , 'secondary' AS source_kind
        , score AS engagement
        , num_comments AS comments
        , published_at
        , matched_keywords
    FROM {{ ref('stg_reddit__posts') }}

    UNION ALL

    SELECT
        item_id
        , 'github' AS source
        , snapshot_date
        , full_name AS title
        , description AS body
        , html_url AS url
        , 'primary' AS source_kind
        , stars AS engagement
        , forks AS comments
        , created_at AS published_at
        , topics AS matched_keywords
    FROM {{ ref('stg_github__repo_snapshots') }}

    UNION ALL

    SELECT
        item_id
        , 'hf_papers' AS source
        , snapshot_date
        , title
        , summary AS body
        , 'https://huggingface.co/papers/' || paper_id AS url
        , 'primary' AS source_kind
        , upvotes AS engagement
        , num_comments AS comments
        , published_at
        , CAST([] AS VARCHAR []) AS matched_keywords
    FROM {{ ref('stg_hf__papers') }}

    UNION ALL

    SELECT
        item_id
        , 'bluesky' AS source
        , snapshot_date
        , LEFT(text, 200) AS title
        , text AS body
        , url
        , 'secondary' AS source_kind
        , like_count + 2 * repost_count AS engagement
        , reply_count AS comments
        , published_at
        , matched_keywords
    FROM {{ ref('stg_bluesky__posts') }}

    UNION ALL

    SELECT
        item_id
        , 'rss' AS source
        , snapshot_date
        , title
        , summary AS body
        , url
        , source_kind
        , NULL AS engagement
        , NULL AS comments
        , published_at
        , matched_keywords
    FROM {{ ref('stg_rss__entries') }}

    UNION ALL

    SELECT
        item_id
        , 'discourse' AS source
        , snapshot_date
        , title
        , excerpt AS body
        , url
        , 'secondary' AS source_kind
        , views + 10 * like_count AS engagement
        , posts_count AS comments
        , published_at
        , CAST([] AS VARCHAR []) AS matched_keywords
    FROM {{ ref('stg_discourse__topics') }}

    UNION ALL

    SELECT
        item_id
        , 'devto' AS source
        , snapshot_date
        , title
        , description AS body
        , url
        , 'secondary' AS source_kind
        , reactions AS engagement
        , comments
        , published_at
        , matched_keywords
    FROM {{ ref('stg_devto__articles') }}

    UNION ALL

    SELECT
        item_id
        , 'lobsters' AS source
        , snapshot_date
        , title
        , NULL AS body
        , url
        , 'secondary' AS source_kind
        , score AS engagement
        , comment_count AS comments
        , published_at
        , matched_keywords
    FROM {{ ref('stg_lobsters__stories') }}
)

SELECT
    item_id || ':' || CAST(snapshot_date AS VARCHAR) AS item_snapshot_id
    , *
FROM unioned
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY item_id, snapshot_date ORDER BY engagement DESC NULLS LAST
) = 1
