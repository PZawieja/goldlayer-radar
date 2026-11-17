{% macro snapshot_date(filename_col='filename') -%}
    CAST(REGEXP_EXTRACT({{ filename_col }}, '(\d{4}-\d{2}-\d{2})', 1) AS DATE)
{%- endmacro %}
