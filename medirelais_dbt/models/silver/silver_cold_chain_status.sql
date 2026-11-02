-- USE CASE 3 - cold-chain proof, per hospital and snapshot day.
-- A hospital can send or receive a cold-chain medicine (insulin, vaccines...) only if
-- every reading of all its fridges over the 7 days before the snapshot stayed between
-- 2 and 8 °C, and its sensors reported in the last 2 days (no data = no proof).
-- Grain: snapshot day x hospital.
WITH snapshots AS (
    SELECT DISTINCT snapshot_date FROM {{ ref('silver_stock') }}
),
window_readings AS (
    SELECT d.snapshot_date, r.*
    FROM snapshots d
    JOIN {{ ref('silver_fridge_readings') }} r
      ON r.reading_at >= DATEADD('day', -7, d.snapshot_date::TIMESTAMP_TZ)
     AND r.reading_at <  d.snapshot_date::TIMESTAMP_TZ
)
SELECT
    d.snapshot_date,
    h.hospital_id,
    h.hospital_name,
    COUNT(w.reading_at)                                             AS readings_7d,
    COUNT(DISTINCT w.device_id)                                     AS fridges_reporting,
    COUNT_IF(w.temp_c < 2 OR w.temp_c > 8)                          AS readings_out_of_range,
    COUNT_IF(w.temp_c < 2 OR w.temp_c > 8) * 5                      AS minutes_out_of_range,
    MIN(w.temp_c)                                                   AS min_temp_c,
    MAX(w.temp_c)                                                   AS max_temp_c,
    MAX(w.reading_at)                                               AS last_reading_at,
    COUNT(w.reading_at) > 0
      AND COUNT_IF(w.temp_c < 2 OR w.temp_c > 8) = 0
      AND MAX(w.reading_at) >= DATEADD('day', -2, d.snapshot_date::TIMESTAMP_TZ) AS cold_chain_ok,
    CASE
        WHEN COUNT(w.reading_at) = 0                                THEN 'no_sensor_data'
        WHEN COUNT_IF(w.temp_c < 2 OR w.temp_c > 8) > 0             THEN 'temperature_excursion'
        WHEN MAX(w.reading_at) < DATEADD('day', -2, d.snapshot_date::TIMESTAMP_TZ) THEN 'sensor_silent'
    END                                                             AS cold_chain_issue
FROM snapshots d
CROSS JOIN {{ ref('silver_hospitals') }} h
LEFT JOIN window_readings w
  ON w.snapshot_date = d.snapshot_date
 AND w.hospital_id   = h.hospital_id
GROUP BY d.snapshot_date, h.hospital_id, h.hospital_name
