-- One row per fridge reading (S5), typed from the raw JSON events.
-- Two firmware versions send the same reading with different keys:
--   v1: {"device_id", "hospital_id", "ts": "2026-10-28T10:05:00Z", "temp_c": 4.8}
--   v2: {"device_id", "hospital_id", "timestamp": 1793182200,      "TEMP": 4.8}
-- Both are read; the same reading loaded twice is kept once.
SELECT
    payload:device_id::STRING                                       AS device_id,
    {{ clean_code('payload:hospital_id::STRING') }}                 AS hospital_id,
    COALESCE(TRY_TO_TIMESTAMP_TZ(payload:ts::STRING),
             TO_TIMESTAMP_TZ(payload:timestamp::NUMBER))            AS reading_at,
    COALESCE(payload:temp_c, payload:TEMP)::FLOAT                   AS temp_c,
    IFF(payload:TEMP IS NOT NULL, 'v2', 'v1')                       AS payload_version,
    _source_file,
    _loaded_at,
    _batch_id
FROM {{ source('bronze', 'fridge_readings_raw') }}
WHERE COALESCE(TRY_TO_TIMESTAMP_TZ(payload:ts::STRING), TO_TIMESTAMP_TZ(payload:timestamp::NUMBER)) IS NOT NULL
  AND COALESCE(payload:temp_c, payload:TEMP) IS NOT NULL
QUALIFY ROW_NUMBER() OVER (PARTITION BY device_id, reading_at ORDER BY _loaded_at DESC) = 1
