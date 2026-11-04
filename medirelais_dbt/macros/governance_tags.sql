-- Classification tags (defined in terraform/tags.tf), set again after every build: dbt recreates
-- the silver and gold tables each night, which drops the tags they carried.
--   - the table: its owner, no personal data, rebuilt daily, and its sensitivity
--   - a purchase-price column, wherever it appears: confidential
-- Runs as a post-hook (dbt_project.yml), so it only executes during dbt run / build.
{% macro governance_tags() %}
    {%- if execute -%}
        {%- set tag = 'MEDIRELAIS.GOVERNANCE.' -%}
        {%- set price_columns = [] -%}
        {%- for col in adapter.get_columns_in_relation(this) -%}
            {%- if col.name | upper == 'UNIT_COST_EUR' -%}{%- do price_columns.append(col.name) -%}{%- endif -%}
        {%- endfor -%}
        {%- for col in price_columns -%}
            {%- do run_query("ALTER TABLE " ~ this ~ " MODIFY COLUMN " ~ col ~ " SET TAG " ~ tag ~ "SENSITIVITY = 'confidential'") -%}
        {%- endfor -%}
        ALTER TABLE {{ this }} SET TAG
            {{ tag }}DATA_OWNER  = 'hadiqa.javaid',
            {{ tag }}PII         = 'none',
            {{ tag }}RETENTION   = 'rebuilt_daily',
            {{ tag }}SENSITIVITY = '{{ "confidential" if price_columns else "internal" }}'
    {%- else -%}
        SELECT 1
    {%- endif -%}
{% endmacro %}
