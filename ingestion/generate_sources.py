"""
MédiRelais - source simulator (the "hospital side" of the pipeline)

Real hospitals do not send clean data. This script plays the role of the
12 hospital pharmacies and produces 3 of our 6 sources, damaged on purpose:

  S1  Pharmacy stock system  -> a Postgres database (schema "pharmacy")
  S2  Daily consumption files -> CSV files in landing/consumption/dt=YYYY-MM-DD/
  S5  Fridge sensors          -> JSON-lines files in landing/sensors/dt=YYYY-MM-DD/

(S3 drug database, S4 shortages and S6 weather are REAL public sources:
 they are downloaded by their own ingestion jobs.)

Each run simulates ONE day:
  --day 1   creates the Postgres tables and the initial stock (full load)
  --day 2+  next days: stock goes down, new batches arrive, some rows are updated
            (this is what the incremental ingestion must pick up)
  --day 3+  schema drift: the consumption files rename qty_used -> quantity_used

Mess level (same idea as the teacher's messy_data.py):
  --mess low | medium | high      about 1 %, 4 % or 10 % of the values are damaged
  --incident corrupted            this day's data is ~40 % broken (incident demo #1)

Same --seed + same --day = exactly the same data, so the demo is reproducible.
Every damage is counted in landing/issues/day_N.json: that is the answer key
to check that silver fixed or quarantined each problem.

Run (inside the container, or with Python 3.10+ and psycopg2 installed):
  python generate_sources.py --day 1
  python generate_sources.py --day 2
  python generate_sources.py --day 3 --incident corrupted
"""
import argparse
import csv
import json
import os
import random
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg2

FIRST_DAY = date(2026, 10, 28)          # day 1 of the simulation
LANDING = Path(os.environ.get("LANDING_DIR", "landing"))
MESS_RATES = {"low": 0.01, "medium": 0.04, "high": 0.10}

# ---------------------------------------------------------------------------
# Reference data: the 12 hospitals and the medicines they stock
# ---------------------------------------------------------------------------
HOSPITALS = [  # id, name, city, beds, latitude, longitude
    ("H01", "Hôpital Saint-Lazare", "Paris", 900, 48.876, 2.325),
    ("H02", "Hôpital des Lilas", "Montreuil", 450, 48.861, 2.443),
    ("H03", "Centre Hospitalier de la Seine", "Asnières-sur-Seine", 600, 48.914, 2.285),
    ("H04", "Hôpital Bellevue", "Saint-Denis", 700, 48.936, 2.358),
    ("H05", "Hôpital du Parc", "Créteil", 550, 48.790, 2.455),
    ("H06", "Hôpital des Tilleuls", "Nanterre", 500, 48.892, 2.207),
    ("H07", "Centre Hospitalier du Val", "Argenteuil", 400, 48.947, 2.248),
    ("H08", "Hôpital Marie-Curie", "Boulogne-Billancourt", 650, 48.835, 2.241),
    ("H09", "Hôpital de l'Ourcq", "Bobigny", 380, 48.909, 2.440),
    ("H10", "Hôpital Les Peupliers", "Versailles", 520, 48.805, 2.120),
    ("H11", "Hôpital Rive Gauche", "Issy-les-Moulineaux", 450, 48.824, 2.273),
    ("H12", "Centre Hospitalier de l'Est", "Noisy-le-Grand", 400, 48.848, 2.553),
]

# id, name, category, unit cost (EUR), cold chain, narcotic, daily use per 100 beds,
# match_keyword = word used in silver to link the product to the real BDPM database
PRODUCTS = [
    ("P001", "Paracetamol 1g tablet", "Analgesic", 0.05, False, False, 60, "PARACETAMOL"),
    ("P002", "Paracetamol 1g IV", "Analgesic", 1.20, False, False, 15, "PARACETAMOL"),
    ("P003", "Ibuprofen 400mg tablet", "Analgesic", 0.08, False, False, 20, "IBUPROFENE"),
    ("P004", "Morphine 10mg injection", "Analgesic", 2.50, False, True, 4, "MORPHINE"),
    ("P005", "Amoxicillin 1g tablet", "Antibiotic", 0.30, False, False, 12, "AMOXICILLINE"),
    ("P006", "Ceftriaxone 1g injection", "Antibiotic", 3.80, False, False, 6, "CEFTRIAXONE"),
    ("P007", "Vancomycin 500mg injection", "Antibiotic", 9.50, False, False, 2, "VANCOMYCINE"),
    ("P008", "Insulin glargine pen", "Diabetes", 24.00, True, False, 3, "INSULINE GLARGINE"),
    ("P009", "Insulin aspart pen", "Diabetes", 18.00, True, False, 3, "INSULINE ASPART"),
    ("P010", "Metformin 1000mg tablet", "Diabetes", 0.10, False, False, 18, "METFORMINE"),
    ("P011", "Enoxaparin 4000 IU syringe", "Anticoagulant", 3.20, False, False, 14, "ENOXAPARINE"),
    ("P012", "Heparin 5000 IU injection", "Anticoagulant", 2.10, False, False, 5, "HEPARINE"),
    ("P013", "Omeprazole 20mg capsule", "Gastro", 0.07, False, False, 25, "OMEPRAZOLE"),
    ("P014", "Ondansetron 8mg injection", "Gastro", 1.90, False, False, 6, "ONDANSETRON"),
    ("P015", "Furosemide 40mg tablet", "Cardio", 0.06, False, False, 10, "FUROSEMIDE"),
    ("P016", "Amiodarone 150mg injection", "Cardio", 4.50, False, False, 1, "AMIODARONE"),
    ("P017", "Adrenaline 1mg injection", "Emergency", 3.00, False, False, 1, "ADRENALINE"),
    ("P018", "Salbutamol inhaler", "Respiratory", 3.50, False, False, 3, "SALBUTAMOL"),
    ("P019", "Epoetin alfa 4000 IU syringe", "Oncology", 85.00, True, False, 0.4, "EPOETINE"),
    ("P020", "Rituximab 500mg vial", "Oncology", 1150.00, True, False, 0.05, "RITUXIMAB"),
    ("P021", "Hepatitis B vaccine", "Vaccine", 12.00, True, False, 0.6, "HEPATITE B"),
    ("P022", "Influenza vaccine", "Vaccine", 8.50, True, False, 1.5, "GRIPPE"),
    ("P023", "Albumin 20% 100ml", "Blood product", 45.00, False, False, 0.8, "ALBUMINE"),
    ("P024", "Sodium chloride 0.9% 500ml", "Fluids", 1.10, False, False, 30, "CHLORURE DE SODIUM"),
    ("P025", "Glucose 5% 500ml", "Fluids", 1.20, False, False, 12, "GLUCOSE"),
]
FRIDGES_PER_HOSPITAL = 2


# ---------------------------------------------------------------------------
# The "mess" helpers: each one damages a value AND counts what it did
# ---------------------------------------------------------------------------
class Mess:
    def __init__(self, rate, rng):
        self.rate = rate
        self.rng = rng
        self.issues = Counter()

    def hit(self):
        return self.rng.random() < self.rate

    def date_text(self, d, field):
        """A date written the way a legacy system might write it."""
        if not self.hit():
            return d.isoformat()
        style = self.rng.choice(["dmy_slash", "compact", "text", "default"])
        self.issues[f"{field}: mixed date format ({style})"] += 1
        if style == "dmy_slash":
            return d.strftime("%d/%m/%Y")
        if style == "compact":
            return d.strftime("%Y%m%d")
        if style == "text":
            return d.strftime("%d %b %Y")
        return "2099-01-01"                     # a "default" date that means nothing

    def number_text(self, n, field):
        """A quantity written as text, sometimes broken."""
        if not self.hit():
            return str(n)
        style = self.rng.choice(["missing", "spaces", "unit", "negative", "huge"])
        self.issues[f"{field}: {style}"] += 1
        if style == "missing":
            return self.rng.choice(["N/A", "null", "-", ""])
        if style == "spaces":
            return f"  {n} "
        if style == "unit":
            return f"{n} units"
        if style == "negative":
            return str(-abs(n) or -1)
        return str(n * 1000)                     # impossible value

    def code(self, value, field, unknown):
        """An identifier with case/space problems, or one that does not exist."""
        if not self.hit():
            return value
        style = self.rng.choice(["case_space", "unknown"])
        self.issues[f"{field}: {style}"] += 1
        return f" {value.lower()} " if style == "case_space" else unknown


# ---------------------------------------------------------------------------
# S1 - the pharmacy stock database (Postgres)
# ---------------------------------------------------------------------------
def pg_connect():
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "pharmacy_source"),
        user=os.environ.get("PGUSER", "source"),
        password=os.environ.get("PGPASSWORD", "source_pw"),
    )


SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS pharmacy;
CREATE TABLE IF NOT EXISTS pharmacy.hospitals (
    hospital_id TEXT PRIMARY KEY, hospital_name TEXT, city TEXT, beds INT,
    latitude NUMERIC(7,3), longitude NUMERIC(7,3),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS pharmacy.products (
    product_id TEXT PRIMARY KEY, product_name TEXT, category TEXT,
    unit_cost_eur NUMERIC(10,2), is_cold_chain BOOLEAN, is_narcotic BOOLEAN,
    match_keyword TEXT, updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
-- A legacy system: quantities and dates are stored as free text (this is where the mess lives)
CREATE TABLE IF NOT EXISTS pharmacy.stock_batches (
    batch_id TEXT PRIMARY KEY, hospital_id TEXT, product_id TEXT,
    qty_on_hand TEXT, expiry_date TEXT, is_recalled TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS stock_batches_updated_at ON pharmacy.stock_batches (updated_at);
"""


def daily_use(product, beds, profile):
    return product[6] * beds / 100 * profile


def build_profiles(rng):
    profile = {(h[0], p[0]): rng.uniform(0.6, 1.4) for h in HOSPITALS for p in PRODUCTS}
    # Planted business cases (kept from the first version of the project)
    profile[("H01", "P008")] = 0.1      # Saint-Lazare barely uses insulin glargine...
    profile[("H04", "P008")] = 2.0      # ...while Bellevue uses a lot -> transfer H01 -> H04
    profile[("H07", "P019")] = 0.0      # Epoetin no longer used at H07
    return profile


def write_stock(cur, day, today, mess, rng, profile, corrupted):
    now = datetime.now(timezone.utc)
    rows = []
    if day == 1:
        cur.executemany(
            "INSERT INTO pharmacy.hospitals VALUES (%s,%s,%s,%s,%s,%s, now()) ON CONFLICT DO NOTHING", HOSPITALS)
        cur.executemany(
            "INSERT INTO pharmacy.products VALUES (%s,%s,%s,%s,%s,%s,%s, now()) ON CONFLICT DO NOTHING",
            [p[:6] + (p[7],) for p in PRODUCTS])
        n = 1
        for h_id, _, _, beds, _, _ in HOSPITALS:
            for p in PRODUCTS:
                avg = daily_use(p, beds, profile[(h_id, p[0])])
                for _ in range(rng.randint(1, 2)):
                    qty = max(int(avg * rng.uniform(10, 30)), 1 if p[3] > 50 else 5)
                    expiry = today + timedelta(days=rng.randint(120, 720))
                    rows.append((f"B{n:05d}", h_id, p[0], qty, expiry, False))
                    n += 1
        # Some ordinary batches getting close to expiry (realistic background)
        for _ in range(15):
            h, p = rng.choice(HOSPITALS), rng.choice(PRODUCTS)
            rows.append((f"B{n:05d}", h[0], p[0], rng.randint(10, 200),
                         today + timedelta(days=rng.randint(35, 90)), False))
            n += 1
        # Planted cases
        planted =[("H01", "P008", 220, 60), ("H02", "P020", 4, 45), ("H05", "P006", 150, 20),
                   ("H03", "P004", 300, 50), ("H09", "P013", 500, -3), ("H10", "P015", 100, 40)]
        for h_id, p_id, qty, days_left in planted:
            rows.append((f"B{n:05d}", h_id, p_id, qty, today + timedelta(days=days_left), False))
            n += 1
        rows.append((f"B{n:05d}", "H06", "P011", 400, today + timedelta(days=55), True))   # recalled
        n += 1
        para = PRODUCTS[0]
        rows.append((f"B{n:05d}", "H03", "P001", int(daily_use(para, 600, profile[("H03", "P001")]) * 200),
                     today + timedelta(days=90), False))                                     # over-stock
    else:
        # Next days: existing batches are consumed, a few new batches are delivered
        cur.execute("SELECT batch_id, hospital_id, product_id, qty_on_hand, expiry_date FROM pharmacy.stock_batches")
        existing = cur.fetchall()
        for batch_id, h_id, p_id, qty_text, expiry_text in rng.sample(existing, k=len(existing) // 10):
            try:
                qty = max(int(qty_text) - rng.randint(1, 20), 0)
            except (TypeError, ValueError):
                qty = rng.randint(5, 50)        # the source system "repairs" its own bad value
            try:
                expiry = date.fromisoformat(expiry_text)
            except (TypeError, ValueError):
                expiry = today + timedelta(days=rng.randint(60, 400))
            rows.append((batch_id, h_id, p_id, qty, expiry, False))
        cur.execute("SELECT count(*) FROM pharmacy.stock_batches")
        n = cur.fetchone()[0] + 1
        for _ in range(15):
            h = rng.choice(HOSPITALS)
            p = rng.choice(PRODUCTS)
            rows.append((f"B{n:05d}", h[0], p[0], rng.randint(10, 300),
                         today + timedelta(days=rng.randint(30, 500)), False))
            n += 1

    # Apply the mess (more of it on an incident day), then upsert into Postgres
    out = []
    for batch_id, h_id, p_id, qty, expiry, recalled in rows:
        if corrupted and rng.random() < 0.4:
            mess.issues["incident: corrupted stock row"] += 1
            qty_text, expiry_text = rng.choice(["-999", "N/A", "abc"]), rng.choice(["31/31/2026", "", "soon"])
        else:
            qty_text = mess.number_text(qty, "stock.qty_on_hand")
            expiry_text = mess.date_text(expiry, "stock.expiry_date")
        out.append((batch_id, mess.code(h_id, "stock.hospital_id", "H99"),
                    mess.code(p_id, "stock.product_id", "P999"), qty_text, expiry_text,
                    rng.choice(["true", "TRUE", "1", "yes"]) if recalled else rng.choice(["false", "0", "no", "False"]),
                    now))
    cur.executemany("""
        INSERT INTO pharmacy.stock_batches VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (batch_id) DO UPDATE SET hospital_id = EXCLUDED.hospital_id,
            product_id = EXCLUDED.product_id, qty_on_hand = EXCLUDED.qty_on_hand,
            expiry_date = EXCLUDED.expiry_date, is_recalled = EXCLUDED.is_recalled,
            updated_at = EXCLUDED.updated_at""", out)
    return len(out)


# ---------------------------------------------------------------------------
# S2 - daily consumption files (one CSV per hospital per day)
# ---------------------------------------------------------------------------
def write_consumption(day, today, mess, rng, profile, corrupted):
    folder = LANDING / "consumption" / f"dt={today.isoformat()}"
    folder.mkdir(parents=True, exist_ok=True)
    qty_col = "quantity_used" if day >= 3 else "qty_used"      # schema drift from day 3
    if day >= 3:
        mess.issues["consumption: schema drift qty_used -> quantity_used"] += 1
    # Day 1 sends 90 days of history, the next days send yesterday only
    days = [today - timedelta(days=d) for d in range(90, 0, -1)] if day == 1 else [today - timedelta(days=1)]
    total = 0
    for h_id, _, _, beds, _, _ in HOSPITALS:
        with open(folder / f"{h_id}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["consumption_date", "hospital_id", "product_id", qty_col])
            for d in days:
                weekend = 0.8 if d.weekday() >= 5 else 1.0
                for p in PRODUCTS:
                    avg = daily_use(p, beds, profile[(h_id, p[0])])
                    qty = max(round(rng.gauss(avg * weekend, avg * 0.25)), 0)
                    if corrupted and rng.random() < 0.4:
                        mess.issues["incident: corrupted consumption row"] += 1
                        row = [rng.choice(["32/13/2026", ""]), h_id, p[0], "-50"]
                    else:
                        row = [mess.date_text(d, "consumption.date"), h_id,
                               mess.code(p[0], "consumption.product_id", "P999"),
                               mess.number_text(qty, "consumption.qty")]
                    w.writerow(row)
                    total += 1
                    if mess.hit():                              # exact duplicate line
                        mess.issues["consumption: duplicate line"] += 1
                        w.writerow(row)
                        total += 1
    return total


# ---------------------------------------------------------------------------
# S5 - fridge temperature sensors (JSON lines, one reading every 5 minutes)
# ---------------------------------------------------------------------------
def write_sensors(day, today, mess, rng):
    folder = LANDING / "sensors" / f"dt={today.isoformat()}"
    folder.mkdir(parents=True, exist_ok=True)
    start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc) - timedelta(days=1)
    total = 0
    # One fridge breaks down for 2 hours on day 2 (use case 3: cold chain)
    broken = ("H04", 1) if day == 2 else None
    with open(folder / "readings.jsonl", "w", encoding="utf-8") as f:
        for h_id, *_ in HOSPITALS:
            for fridge in range(1, FRIDGES_PER_HOSPITAL + 1):
                for step in range(0, 24 * 60, 5):
                    ts = start + timedelta(minutes=step)
                    temp = round(rng.gauss(5.0, 0.7), 2)
                    if broken == (h_id, fridge) and 600 <= step < 720:
                        temp = round(rng.uniform(9, 12), 2)
                    event = {"device_id": f"{h_id}-FRIDGE-{fridge}", "hospital_id": h_id,
                             "ts": ts.isoformat().replace("+00:00", "Z"), "temp_c": temp}
                    if mess.hit():                      # a firmware version sends other keys
                        mess.issues["sensors: renamed keys (TEMP, timestamp)"] += 1
                        event = {"device_id": event["device_id"], "hospital_id": h_id,
                                 "timestamp": int(ts.timestamp()), "TEMP": temp}
                    f.write(json.dumps(event) + "\n")
                    total += 1
    return total


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", type=int, default=1)
    ap.add_argument("--mess", choices=MESS_RATES, default="medium")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--incident", choices=["none", "corrupted"], default="none")
    ap.add_argument("--skip-postgres", action="store_true", help="only write the files (S2, S5)")
    a = ap.parse_args()

    rng = random.Random(a.seed * 1000 + a.day)
    profile = build_profiles(random.Random(a.seed))       # same habits every day
    mess = Mess(MESS_RATES[a.mess], rng)
    corrupted = a.incident == "corrupted"
    today = FIRST_DAY + timedelta(days=a.day - 1)
    print(f"Simulating day {a.day} ({today}), mess={a.mess}, incident={a.incident}, seed={a.seed}")

    if not a.skip_postgres:
        with pg_connect() as pg, pg.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            n = write_stock(cur, a.day, today, mess, rng, profile, corrupted)
        print(f"  S1 Postgres pharmacy.stock_batches: {n} rows inserted or updated")
    n = write_consumption(a.day, today, mess, rng, profile, corrupted)
    print(f"  S2 consumption files: {n} lines in {LANDING}/consumption/dt={today}/")
    n = write_sensors(a.day, today, mess, rng)
    print(f"  S5 sensor readings: {n} events in {LANDING}/sensors/dt={today}/")

    report = LANDING / "issues" / f"day_{a.day}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"day": a.day, "date": today.isoformat(), "seed": a.seed, "mess": a.mess,
                                  "incident": a.incident, "issues": dict(sorted(mess.issues.items()))}, indent=2))
    print(f"  {sum(mess.issues.values())} problems injected -> answer key: {report}")


if __name__ == "__main__":
    main()
