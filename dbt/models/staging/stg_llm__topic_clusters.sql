SELECT
    topic_key
    , cluster_key
    , cluster_label
    , clustered_at
FROM {{ source('llm', 'topic_clusters') }}
