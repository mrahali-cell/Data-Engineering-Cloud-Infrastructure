"""S6 · Real weather from the Open-Meteo API -> Snowflake bronze. Method: REST API PULL -> VARIANT.

Why: fridge alarms and drug demand (heat waves, flu season) depend on the weather at each
hospital. Open-Meteo is free, needs no key, and answers JSON.
For each hospital (coordinates read from BRONZE.HOSPITALS_RAW, loaded by S1) we ask for
yesterday + the next 2 days, hourly temperature, and store the response untouched.
Good API habits shown here: timeout, retries with a delay, raise_for_status (fail loudly).
"""
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import BRONZE, run_job, with_retries  # noqa: E402

API = "https://api.open-meteo.com/v1/forecast"


def body(cur, batch_id):
    cur.execute(f"SELECT DISTINCT hospital_id, latitude, longitude FROM {BRONZE}.HOSPITALS_RAW "
                "WHERE latitude IS NOT NULL ORDER BY 1")
    hospitals = cur.fetchall()
    if not hospitals:
        raise RuntimeError("no hospital coordinates yet: run ingest_stock_postgres.py first")
    loaded = 0
    for hospital_id, lat, lon in hospitals:
        params = {"latitude": float(lat), "longitude": float(lon), "hourly": "temperature_2m",
                  "past_days": 1, "forecast_days": 2, "timezone": "UTC"}

        def call():
            r = requests.get(API, params=params, timeout=30)
            r.raise_for_status()
            return r
        r = with_retries(call, what=f"weather for {hospital_id}")
        cur.execute(f"INSERT INTO {BRONZE}.WEATHER_RAW SELECT %s, %s, PARSE_JSON(%s), CURRENT_TIMESTAMP(), %s",
                    (hospital_id, r.url, json.dumps(r.json()), batch_id))
        loaded += 1
    print(f"  {loaded} hospitals, {loaded} API responses stored")
    return len(hospitals), loaded


if __name__ == "__main__":
    run_job("s6_weather_api", body)
