-- One row per hospital, typed from the all-text bronze table.
-- If the file was loaded more than once, the latest load wins.
SELECT
    hospital_id,
    hospital_name,
    city,
    TRY_TO_NUMBER(beds) AS beds
FROM {{ source('bronze', 'hospitals') }}
QUALIFY ROW_NUMBER() OVER (PARTITION BY hospital_id ORDER BY _loaded_at DESC) = 1
