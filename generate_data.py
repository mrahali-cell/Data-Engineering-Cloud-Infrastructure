"""
MédiRelais - fake data generator
Creates 4 CSV files in a folder called "data":
  - hospitals.csv     : the 12 hospitals of the network
  - products.csv      : the medication catalogue
  - stock.csv         : SOURCE 1 - what is on each pharmacy shelf today (one row per batch)
  - consumption.csv   : SOURCE 2 - how much each hospital used per day (last 90 days)

Only uses Python's built-in libraries: no pip install needed.
Run it with:  python generate_data.py
"""

import csv
import os
import random
from datetime import date, timedelta

random.seed(42)  # same "random" data every time you run it

SNAPSHOT_DATE = date(2026, 10, 28)  # "today" in our fake world
HISTORY_DAYS = 90                   # days of consumption history
OUTPUT_FOLDER = "data"

# ---------------------------------------------------------------
# 1. Hospitals
# ---------------------------------------------------------------
HOSPITALS = [
    ("H01", "Hôpital Saint-Lazare", "Paris", 900),
    ("H02", "Hôpital des Lilas", "Montreuil", 450),
    ("H03", "Centre Hospitalier de la Seine", "Asnières-sur-Seine", 600),
    ("H04", "Hôpital Bellevue", "Saint-Denis", 700),
    ("H05", "Hôpital du Parc", "Créteil", 550),
    ("H06", "Hôpital des Tilleuls", "Nanterre", 500),
    ("H07", "Centre Hospitalier du Val", "Argenteuil", 400),
    ("H08", "Hôpital Marie-Curie", "Boulogne-Billancourt", 650),
    ("H09", "Hôpital de l'Ourcq", "Bobigny", 380),
    ("H10", "Hôpital Les Peupliers", "Versailles", 520),
    ("H11", "Hôpital Rive Gauche", "Issy-les-Moulineaux", 450),
    ("H12", "Centre Hospitalier de l'Est", "Noisy-le-Grand", 400),
]

# ---------------------------------------------------------------
# 2. Products: (id, name, category, unit_cost_eur, cold_chain, narcotic, avg_daily_use_per_100_beds)
# ---------------------------------------------------------------
PRODUCTS = [
    ("P001", "Paracetamol 1g tablet", "Analgesic", 0.05, False, False, 60),
    ("P002", "Paracetamol 1g IV", "Analgesic", 1.20, False, False, 15),
    ("P003", "Ibuprofen 400mg tablet", "Analgesic", 0.08, False, False, 20),
    ("P004", "Morphine 10mg injection", "Analgesic", 2.50, False, True, 4),
    ("P005", "Amoxicillin 1g tablet", "Antibiotic", 0.30, False, False, 12),
    ("P006", "Ceftriaxone 1g injection", "Antibiotic", 3.80, False, False, 6),
    ("P007", "Vancomycin 500mg injection", "Antibiotic", 9.50, False, False, 2),
    ("P008", "Insulin glargine pen", "Diabetes", 24.00, True, False, 3),
    ("P009", "Insulin aspart pen", "Diabetes", 18.00, True, False, 3),
    ("P010", "Metformin 1000mg tablet", "Diabetes", 0.10, False, False, 18),
    ("P011", "Enoxaparin 4000 IU syringe", "Anticoagulant", 3.20, False, False, 14),
    ("P012", "Heparin 5000 IU injection", "Anticoagulant", 2.10, False, False, 5),
    ("P013", "Omeprazole 20mg capsule", "Gastro", 0.07, False, False, 25),
    ("P014", "Ondansetron 8mg injection", "Gastro", 1.90, False, False, 6),
    ("P015", "Furosemide 40mg tablet", "Cardio", 0.06, False, False, 10),
    ("P016", "Amiodarone 150mg injection", "Cardio", 4.50, False, False, 1),
    ("P017", "Adrenaline 1mg injection", "Emergency", 3.00, False, False, 1),
    ("P018", "Salbutamol inhaler", "Respiratory", 3.50, False, False, 3),
    ("P019", "Epoetin alfa 4000 IU syringe", "Oncology", 85.00, True, False, 0.4),
    ("P020", "Rituximab 500mg vial", "Oncology", 1150.00, True, False, 0.05),
    ("P021", "Hepatitis B vaccine", "Vaccine", 12.00, True, False, 0.6),
    ("P022", "Influenza vaccine", "Vaccine", 8.50, True, False, 1.5),
    ("P023", "Albumin 20% 100ml", "Blood product", 45.00, False, False, 0.8),
    ("P024", "Sodium chloride 0.9% 500ml", "Fluids", 1.10, False, False, 30),
    ("P025", "Glucose 5% 500ml", "Fluids", 1.20, False, False, 12),
]

# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------
def write_csv(filename, header, rows):
    path = os.path.join(OUTPUT_FOLDER, filename)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"  {filename:<18} {len(rows):>6} rows")


def daily_use(product, beds):
    """Average daily consumption of a product in a hospital of this size."""
    return product[6] * beds / 100


# ---------------------------------------------------------------
# 3. Consumption (SOURCE 2): one row per hospital x product x day
# ---------------------------------------------------------------
# Each hospital uses some products more or less than average (its "profile")
profile = {}
for h in HOSPITALS:
    for p in PRODUCTS:
        profile[(h[0], p[0])] = random.uniform(0.6, 1.4)

# Planted case for use case 1: H01 barely uses insulin glargine, H04 uses a lot
profile[("H01", "P008")] = 0.1
profile[("H04", "P008")] = 2.0
# Planted case: H07 has stopped using Epoetin (zero consumption -> excluded from cover)
profile[("H07", "P019")] = 0.0

consumption_rows = []
for h_id, _, _, beds in HOSPITALS:
    for p in PRODUCTS:
        avg = daily_use(p, beds) * profile[(h_id, p[0])]
        for d in range(HISTORY_DAYS, 0, -1):
            day = SNAPSHOT_DATE - timedelta(days=d)
            weekend_factor = 0.8 if day.weekday() >= 5 else 1.0
            qty = round(random.gauss(avg * weekend_factor, avg * 0.25))
            consumption_rows.append([day.isoformat(), h_id, p[0], max(qty, 0)])

# ---------------------------------------------------------------
# 4. Stock (SOURCE 1): one row per batch on the shelf today
# ---------------------------------------------------------------
stock_rows = []
batch_counter = 1


def add_batch(h_id, p_id, qty, expiry, recalled=False):
    global batch_counter
    stock_rows.append([
        SNAPSHOT_DATE.isoformat(), h_id, p_id, f"B{batch_counter:05d}",
        qty, expiry.isoformat(), recalled,
    ])
    batch_counter += 1


for h_id, _, _, beds in HOSPITALS:
    for p in PRODUCTS:
        avg = daily_use(p, beds) * profile[(h_id, p[0])]
        # 1 to 2 batches per product, normally 20-60 days of stock in total
        for _ in range(random.randint(1, 2)):
            days_of_stock = random.uniform(10, 30)
            qty = max(int(avg * days_of_stock), 1 if p[3] > 50 else 5)
            expiry = SNAPSHOT_DATE + timedelta(days=random.randint(120, 720))
            add_batch(h_id, p[0], qty, expiry)

# Some normal batches that are getting close to expiry (realistic noise)
for _ in range(15):
    h_id = random.choice(HOSPITALS)[0]
    p = random.choice(PRODUCTS)
    add_batch(h_id, p[0], random.randint(10, 200), SNAPSHOT_DATE + timedelta(days=random.randint(35, 90)))

# ---- Planted cases (so the dashboard has a story to tell) ----
# UC1: H01 holds 220 insulin glargine pens expiring in 60 days (~€5,280 at risk),
#      while H04 uses a lot of it -> transfer suggestion H01 -> H04
add_batch("H01", "P008", 220, SNAPSHOT_DATE + timedelta(days=60))
# UC1: expensive oncology vial expiring in 45 days at H02
add_batch("H02", "P020", 4, SNAPSHOT_DATE + timedelta(days=45))
# UC1 exclusion: only 20 days left -> too late to transfer (rule: >= 30 days)
add_batch("H05", "P006", 150, SNAPSHOT_DATE + timedelta(days=20))
# UC1 exclusion: narcotic expiring soon -> never transferred
add_batch("H03", "P004", 300, SNAPSHOT_DATE + timedelta(days=50))
# UC1 exclusion: recalled batch -> never transferred
add_batch("H06", "P011", 400, SNAPSHOT_DATE + timedelta(days=55), recalled=True)
# UC1 exclusion: already expired
add_batch("H09", "P013", 500, SNAPSHOT_DATE - timedelta(days=3))
# UC1 exclusion: value under €200 (100 x €0.06 = €6)
add_batch("H10", "P015", 100, SNAPSHOT_DATE + timedelta(days=40))
# UC2: H03 is over-stocked on paracetamol: ~200 days of cover, but it expires in 90 days
h03_beds = 600
para = PRODUCTS[0]
para_avg = daily_use(para, h03_beds) * profile[("H03", "P001")]
add_batch("H03", "P001", int(para_avg * 200), SNAPSHOT_DATE + timedelta(days=90))

# ---------------------------------------------------------------
# 5. Write everything
# ---------------------------------------------------------------
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
print(f"Writing files to ./{OUTPUT_FOLDER}/")

write_csv("hospitals.csv",
          ["hospital_id", "hospital_name", "city", "beds"],
          HOSPITALS)
write_csv("products.csv",
          ["product_id", "product_name", "category", "unit_cost_eur", "is_cold_chain", "is_narcotic"],
          [p[:6] for p in PRODUCTS])
write_csv("stock.csv",
          ["snapshot_date", "hospital_id", "product_id", "batch_id", "qty_on_hand", "expiry_date", "is_recalled"],
          stock_rows)
write_csv("consumption.csv",
          ["consumption_date", "hospital_id", "product_id", "qty_used"],
          consumption_rows)

print("Done.")
