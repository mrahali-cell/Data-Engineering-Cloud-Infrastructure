-- One row per hospital (S1, already typed in the source database).
-- If the hospital was loaded more than once, the latest load wins.
SELECT
    {{ clean_code('hospital_id') }} AS hospital_id,
    hospital_name,
    city,
    beds,
    latitude,
    longitude
FROM {{ source('bronze', 'hospitals_raw') }}
QUALIFY ROW_NUMBER() OVER (PARTITION BY {{ clean_code('hospital_id') }} ORDER BY _loaded_at DESC) = 1
