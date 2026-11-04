-- Generic test: the column stays between min_value and max_value (both included).
-- Same idea as dbt_utils.accepted_range, written here so the project needs no package.
-- The test FAILS if this query returns rows.
{% test accepted_range(model, column_name, min_value=none, max_value=none) %}
SELECT *
FROM {{ model }}
WHERE {{ column_name }} IS NOT NULL
  AND (FALSE
       {% if min_value is not none %} OR {{ column_name }} < {{ min_value }} {% endif %}
       {% if max_value is not none %} OR {{ column_name }} > {{ max_value }} {% endif %})
{% endtest %}
