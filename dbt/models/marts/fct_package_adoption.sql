SELECT
    package_snapshot_id
    , package
    , snapshot_date
    , last_day
    , last_week
    , last_month
    , ROUND(last_week * 30.0 / 7 / NULLIF(last_month, 0), 3) AS weekly_vs_monthly_run_rate
FROM {{ ref('stg_pypi__downloads') }}
