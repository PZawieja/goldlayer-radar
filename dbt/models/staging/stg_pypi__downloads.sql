SELECT
    package || ':' || CAST({{ snapshot_date() }} AS VARCHAR) AS package_snapshot_id
    , package
    , {{ snapshot_date() }} AS snapshot_date
    , last_day
    , last_week
    , last_month
    , collected_at
FROM {{ source('raw', 'pypi') }}
