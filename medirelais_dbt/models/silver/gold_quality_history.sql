{{ config(schema='GOLD') }}
-- Pipeline tab of the team dashboard: consumption rows received per nightly delivery (dt= folder),
-- by reject reason (NULL = clean). Same rule as the quality gate: duplicates are not errors.
-- In the silver folder so it is rebuilt every night, even when the quality gate blocks gold.
SELECT
    REGEXP_SUBSTR(_source, 'dt=([0-9-]+)', 1, 1, 'e', 1)::DATE   AS delivery_date,
    COALESCE(reject_reason, 'clean')                             AS row_status,
    reject_reason IS NOT NULL AND reject_reason <> 'duplicate_row' AS is_rejected,
    COUNT(*)                                                     AS rows_received
FROM {{ ref('silver_consumption_checked') }}
GROUP BY 1, 2, 3
