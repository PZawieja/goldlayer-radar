SELECT
    cluster_key
    , ANY_VALUE(cluster_label) AS cluster_label
    , COUNT(*) AS topic_keys
    , MIN(clustered_at) AS first_clustered_at
FROM {{ ref('stg_llm__topic_clusters') }}
GROUP BY cluster_key
