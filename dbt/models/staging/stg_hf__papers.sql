SELECT
    'hf:' || paper_id AS item_id
    , paper_id
    , {{ snapshot_date() }} AS snapshot_date
    , title
    , summary
    , upvotes
    , num_comments
    , published_at
    , collected_at
FROM {{ source('raw', 'hf_papers') }}
