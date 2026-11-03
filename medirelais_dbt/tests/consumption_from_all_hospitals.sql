{{ config(severity='warn') }}
-- README: each hospital pharmacy sends its daily consumption every night.
-- A hospital with no clean line in the latest delivery lowers its daily use,
-- so days of cover and transfer receivers would be wrong for it.
-- The test FAILS (warns) with one row per missing hospital.
WITH cons AS (
    SELECT REGEXP_SUBSTR(_source, 'dt=([0-9-]+)', 1, 1, 'e', 1) AS delivery, hospital_id, reject_reason
    FROM {{ ref('silver_consumption_checked') }}
),
latest AS (
    SELECT DISTINCT hospital_id
    FROM cons
    WHERE delivery = (SELECT MAX(delivery) FROM cons)
      AND reject_reason IS NULL
)
SELECT h.hospital_id AS hospital_missing_tonight
FROM {{ ref('silver_hospitals') }} h
LEFT JOIN latest l USING (hospital_id)
WHERE l.hospital_id IS NULL
