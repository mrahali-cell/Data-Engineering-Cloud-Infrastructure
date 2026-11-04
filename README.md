# Data-Engineering-Cloud-Infrastructure
# MédiRelais

**Saving hospital medication before it expires.**

MédiRelais runs a shared stock platform for a group of 12 public hospitals in Île-de-France. It spots medication close to expiry in one hospital pharmacy and moves it to a hospital that will use it in time.

> Fictional company built for the *Data Engineering & Cloud Infrastructure* course (Albert School, 2026). All figures are assumptions, stated explicitly so they can be challenged.

---

## 1. The company

### Customers and revenue model

| Who pays | What they buy | Price (assumption) | Per year |
| --- | --- | --- | --- |
| Each member hospital (12) | Platform subscription: alerts, matching, dashboards | €1,500 / month | €216,000 |
| **Total revenue** | | | **€216,000** |

MédiRelais is paid a flat subscription only. It takes no percentage and no fee on the medication that moves between
hospitals: in France a platform cannot charge a success fee or a commission on the redistribution of medication between
hospitals. The savings are shown to the hospitals, not billed: about €576,000 a year saved (target below) for €216,000
of subscriptions.

### Operations, size and stakeholders

- **Team of 6:** CEO, hospital pharmacist (clinical lead), logistics coordinator, 2 data engineers, 1 account manager.
- **Network:** 12 hospitals of one hospital group (GHT, *groupement hospitalier de territoire*), about 6,500 beds.
- **Data:** each hospital pharmacy sends a nightly stock extract from its pharmacy system, plus daily consumption and orders. National public data (drug database, shortages) completes it.
- **Logistics:** transfers ride the group's existing courier route, twice a week, so no new trucks are needed.
- **Stakeholders:**
  - hospital pharmacists, who decide and sign transfers;
  - pharmacy buyers, who place orders;
  - finance directors, who want the savings;
  - the courier service;
  - the regional health agency (ARS), which sets the rules.

### The problem, in numbers (assumptions)

| Assumption | Value |
| --- | --- |
| Medication purchases per hospital per year | €8 M (€96 M for the network) |
| Share of purchases that expires before use | 1.5% |
| Medication value thrown away per year | ≈ €1.44 M |
| Share MédiRelais can save by transferring | 40% |
| Value saved per year (target) | ≈ €576,000 |
| Products listed per hospital pharmacy | ≈ 2,500 |

### Transfer rules (constraints)

- Only batches with **30 days or more** left before expiry can be transferred.
- Minimum transfer value is **€200**, so the courier trip is worth it.
- Cold-chain products (insulin, vaccines...) would need proof they stayed between **2 °C and 8 °C** the whole time. We have no fridge data in this project, so they are **never** transferred and are shown as "no cold-chain proof".
- Narcotics and recalled batches are **never** transferred.
- Transfers stay **inside the hospital group**, under a pharmacist's responsibility.
- **No patient data** is used: only stock, orders and consumption.

---

## 2. Use cases and business value

Two use cases carry the business case:
- the first saves medication that is about to expire;
- the second stops hospitals from over-ordering in the first place.

### Use case 1 · Expiry alert and transfer matching (core)

| | |
| --- | --- |
| **Decision** | Which batches to send to which hospital this week |
| **Users** | Hospital pharmacist (validates each transfer); group logistics coordinator (plans the courier route) |
| **Frequency** | Daily at 06:00, after the nightly stock extracts land and before pharmacies open at 08:00. Expiry moves day by day, so a weekly run would miss short windows. |

**Metric 1 · Value at risk:** the stock value that will expire within 90 days.

```
value_at_risk = SUM(qty_on_hand × unit_cost)
                WHERE expiry_date <= snapshot_date + 90 days
```

- **Grain:** one row per batch × hospital × snapshot day.
- **Exclusions:** narcotics, recalled batches, batches already expired.
- Each batch also carries the reason it cannot be transferred, if any: under 30 days left, under €200, or no cold-chain proof.

**Metric 2 · Saveable value:** what the dashboard shows.

```
usable_qty     = MIN(qty_on_hand,
                     receiver's daily use × days left − receiver's own stock that expires first)
saveable_value = SUM(usable_qty × unit_cost) of suggested transfers
```

- **Grain:** one row per suggested batch × snapshot day.
- **Daily use:** average over the last 28 days, counting only the days actually reported (a day whose line went to quarantine is unknown, not zero).
- **Receiver:** among the other hospitals that use the product, the one that can use the most of the batch before it expires; ties broken by daily use, then hospital ID. A hospital that has run out of the product still counts. A batch no hospital can use in time gets no suggestion. Cold-chain batches are never suggested.
- **Priority:** medicines in national shortage first (S4), then the largest saveable value.
- **Assumption:** every hospital uses its soonest-expiring stock first. When several batches go to the same hospital, `can_use_before_expiry` checks whether it can use all of them, plus its own stock, in time.
- **Value saved**, what shows each hospital the return on its subscription, counts the units that were actually transferred and used before expiry. It needs a register of real transfers, which is out of scope for this project. Saveable value is its forecast.

**Metric 3 · Recovery rate:** the share of the value at risk that the suggested transfers can save.

```
recovery_rate = saveable_value / value_at_risk
```

- **Grain:** one number per snapshot day, for the whole network (dashboard key number).
- It shows how much of the problem MédiRelais can actually solve; the README target is 40 %.

**Acceptance test** (`tests/acceptance_planted_cases.sql`), on the generated dataset (seed 42, snapshot 28 Oct 2026), whose planted cases were checked by hand from the CSV files:
- total value at risk is €146,658.16 over 20 batches, to the cent;
- the H01 insulin and H02 rituximab batches are at risk but never transferred (cold chain);
- the 20-day ceftriaxone and the €6 furosemide batches are not transferable;
- the narcotic, the recalled and the expired batches never appear;
- no suggested transfer breaks a transfer rule (`tests/transfers_respect_rules.sql`).

### Use case 2 · Stock cover and smarter ordering

| | |
| --- | --- |
| **Decision** | How much of each product to order next week |
| **User** | The pharmacy buyer of each hospital |
| **Frequency** | Weekly, every Monday, because orders are placed once a week |

**Metric · Days of cover:** how many days the current stock lasts at the normal pace.

```
days_of_cover = qty_on_hand / AVG(daily_consumption over the last 28 days)
```

- **Grain:** one row per product × hospital × day.
- **Window:** the 28 days before each snapshot date, so re-running an old day gives the same answer.
- **Exclusions:** products with less than 8 weeks of history, and products with zero consumption.
- **Alert:** some of the stock will expire before it is used. Batches are used soonest-expiring first, and a batch is flagged when everything ahead of it, plus the batch itself, takes longer to use than the batch has left.

**Metric · Over-stock value:** the money that will expire unused if the buyer keeps the current stock.

```
overstock_value = SUM(units that will expire before use at the current pace × unit_cost)
units_expiring  = MIN(qty_on_hand, MAX(0, stock queued up to this batch − daily use × days to expiry))
```

- **Grain:** one row per product × hospital × day (`gold_days_of_cover.overstock_value_eur`).
- **Daily use** is the same 28-day average as above; the dashboard shows it next to days of cover.

**Acceptance test** (same file as use case 1):
- for 3 sample products, the computed cover equals a manual calculation (17, 45 and 41 days);
- H03 paracetamol, deliberately over-stocked in the test data, is flagged;
- H07 epoetin (zero use) and H12 albumin (only 35 days of history) are excluded.

---

## 3. Architecture

*Diagram coming next: 4 sources → ingestion (Docker) → bronze / silver / gold (dbt in Snowflake) → dashboard (Streamlit).*

### Sources and ingestion

Four sources, each with the ingestion method that fits it. All code is in [`ingestion/`](ingestion/) (one Docker image, one job per source).

| # | Source | Real? | Ingestion method | Bronze table(s) |
| --- | --- | --- | --- | --- |
| S1 | Pharmacy stock system (Postgres) | simulated, messy | incremental pull on `updated_at` + `MERGE` | `HOSPITALS_RAW`, `PRODUCTS_RAW`, `STOCK_RAW` |
| S2 | Daily consumption files | simulated, messy | batch files → stage → `COPY INTO`, columns matched by name | `CONSUMPTION_RAW` |
| S3 | BDPM public drug database: medicines, boxes and their molecules | **real** | weekly download, full refresh | `BDPM_SPECIALITES_RAW`, `BDPM_PRESENTATIONS_RAW`, `BDPM_COMPOSITION_RAW` |
| S4 | BDPM shortages file | **real** | daily pull, change detection (row hash + `MERGE`) | `SHORTAGES_RAW` |

Every bronze row carries `_source` (or `_source_file`), `_loaded_at` and `_batch_id`; every job run is logged in `MEDIRELAIS.BRONZE.LOAD_RUNS`.

**Same medicine, different names.** S3 links each product to the national codes (CIS) of every medicine that contains
its molecule: by the composition file (`CIS_COMPO_bdpm.txt`, which finds brand names such as Doliprane for paracetamol)
and by name (generics such as "Paracétamol Biogaran"). That link is what joins our products to the shortage list (S4).

*Scope change (2 Nov 2026): the project keeps use cases 1 and 2. The fridge sensors (cold chain, formerly use case 3) and
the weather API were removed, so the pipeline has 4 sources.*

### Repository structure

```
README.md            company, use cases, architecture, how to run, team
airflow/             orchestration: the daily DAG, its check scripts, docker-compose
ingestion/           4 sources -> bronze: source simulator, one job per source, Dockerfile, docker-compose
medirelais_dbt/      dbt project: silver (cleaning, quarantine) and gold (metrics), tests
snowflake/           setup, scheduling and access-check scripts
streamlit/           dashboard
terraform/           infrastructure as code: Snowflake platform, access rules, AWS archive
data/, generate_data.py, snowflake/02_load_bronze.sql
                     first CSV version; to retire once silver reads the new bronze tables
```

### About the data

The data is generated by `generate_data.py` (fixed seed, so every run gives the same files). It is a **sample**, not the full network:

| | In the sample | Real network (assumptions above) |
| --- | --- | --- |
| Products | 25 | ≈ 2,500 per hospital pharmacy |
| Stock on the shelves | ≈ €1.07 M | ≈ €96 M of purchases a year |
| Hospitals | 12 | 12 |

The business figures in section 1 are about the real network. The numbers on the dashboard are about the sample.

Bronze keeps every value as text, exactly as received, with `_source`, `_loaded_at` and `_batch_id`. Silver types the values. A row that fails a check is not dropped silently: it goes to `silver_stock_quarantine` or `silver_consumption_quarantine` with a `reject_reason`. Gold reads from silver only.

### Data governance

**What data the platform holds.** No patient data and no personal data: only stock, consumption per hospital
and product, and the public drug database. The sensitive data is commercial: the purchase prices each
hospital negotiated.

**Who sees what** (enforced by Snowflake itself, defined in [`terraform/governance.tf`](terraform/governance.tf)):

| Role | Who | Sees |
| --- | --- | --- |
| `MEDIRELAIS_PHARMACIST_Hxx` | A hospital pharmacist | Its own hospital's stock at risk and cover, and the transfers it sends or receives |
| `MEDIRELAIS_READER` | The dashboard, the logistics coordinator | Every hospital, no purchase prices, GOLD only |
| `MEDIRELAIS_FINANCE` | Finance | Every hospital, with purchase prices |
| `MEDIRELAIS_PIPELINE` | Airflow and dbt | Everything; the only role that writes |

[`snowflake/04_access_check.sql`](snowflake/04_access_check.sql) runs the same query under each role, and lists
who read the gold tables in the last 7 days.

**Administrators.** Account administration (`ACCOUNTADMIN`: users, roles, billing, account settings) is held by
Soumaya Atoui and Hadiqa Javaid. Manel Rahali works as `SYSADMIN` (databases, schemas, warehouses).

**Data stewards**, accountable for the definitions and the quality of each layer:

| Layer | Steward |
| --- | --- |
| Sources and bronze (S1 to S4, ingestion jobs) | Manel Rahali |
| Silver and gold (cleaning, quarantine, metrics, tests) | Hadiqa Javaid |
| Access rules, platform, archive and costs | Soumaya Atoui |

## 4. How to run

**Ingestion (4 sources → bronze)**, with Docker Desktop running. Details in [`ingestion/README.md`](ingestion/README.md).

```bash
cd ingestion
cp .env.example .env                        # SNOWFLAKE_USER = your LOGIN_NAME
docker compose run --rm keygen              # prints the ALTER USER line to run once in Snowflake
docker compose up -d pharmacy-db
docker compose run --rm ingest python run_all.py --day 1    # then --day 2, 3...
```

**After every `git pull`**, rebuild the image before running anything: the code is copied *into* the image, so
without a rebuild Docker keeps running the old code.

```bash
git checkout main && git pull
cd ingestion
docker compose build ingest                 # puts the new code in the image
docker compose run --rm ingest python jobs/bootstrap_snowflake.py   # creates any new bronze table (safe to re-run)
```

**What happens when you run an ingestion command**

```
GitHub (code)  ->  your laptop: Docker runs the job  ->  Snowflake BRONZE (data)  ->  dbt in Snowflake (silver, gold)
```

1. `docker compose run --rm ingest ...` starts a container from the `medirelais-ingest` image (Python, libraries and
   the code), after checking that the hospitals' Postgres database (`pharmacy-db`) is up.
2. The job connects to Snowflake with your key pair: `.env` says which account, user and role, and `keys/rsa_key.p8`
   proves it is you. No password.
3. Each job gets its data the way its source works:
   - S1: reads only the stock rows changed since the last run, then `MERGE`;
   - S2: uploads the nightly files to a stage, then `COPY INTO`;
   - S3: downloads the 3 BDPM files, then `TRUNCATE` + `COPY INTO` (weekly full refresh);
   - S4: downloads the shortage list, hashes each row and `MERGE`s to see what is new or ended.
4. Every row gets `_source_file` (or `_source`), `_loaded_at` and `_batch_id`, and the job writes one line to
   `MEDIRELAIS.BRONZE.LOAD_RUNS`: status, rows read, rows loaded. Rows read = rows loaded means nothing was lost.
5. The jobs only fill **bronze**. Silver and gold are built by dbt **inside Snowflake**: every day at 06:00 by the task
   `DAILY_PIPELINE`, or at once with `run_all.py --dbt`.

**Orchestration (Airflow).** Every morning at 06:00, the DAG `medirelais_daily` runs the 4 ingestion jobs in parallel,
checks them, builds silver, runs a quality gate, then builds gold; a failed step is retried, then stops everything after
it. Setup, tasks and incident demos: [`airflow/README.md`](airflow/README.md).

**Deploying new dbt code** (after a merge that changes `medirelais_dbt/`): run `snowflake/03_schedule.sql` as
`MEDIRELAIS_PIPELINE`. It pulls `main` from GitHub, redeploys the dbt project and runs it. If the merge also adds a
bronze table, run the ingestion steps above first, or dbt fails because the table does not exist yet.

**Looking at the data in Snowflake**

- Browse: in a workspace, the **Databases** tab (next to Workspaces) → **MEDIRELAIS → BRONZE / SILVER / GOLD → Tables**;
  or **Catalog → Database Explorer** in the left menu, open a table, then **Data Preview**.
- Query: open a worksheet, pick the role `SYSADMIN` and the warehouse `MEDIRELAIS_WH`, then for example:

```sql
SELECT * FROM MEDIRELAIS.BRONZE.LOAD_RUNS ORDER BY run_at DESC;                      -- last ingestion runs
SELECT * FROM MEDIRELAIS.SILVER.SILVER_STOCK_QUARANTINE;                             -- rejected rows and why
SELECT * FROM MEDIRELAIS.SILVER.SILVER_PRODUCT_REFERENCE;                            -- national codes, shortages
SELECT * FROM MEDIRELAIS.GOLD.GOLD_TRANSFER_SUGGESTIONS ORDER BY snapshot_date DESC, priority_rank;
SELECT * FROM MEDIRELAIS.GOLD.GOLD_DAYS_OF_COVER WHERE is_overstock_alert;
```

**First CSV version** (kept until silver is moved to the new bronze tables):

1. `python generate_data.py` writes the CSV files to `data/`.
2. An admin runs `snowflake/01_setup.sql` once. It creates the warehouse, the database, the bronze tables, the `MEDIRELAIS_PIPELINE` role and the link to this GitHub repo.
3. Upload the CSV files to `@MEDIRELAIS.BRONZE.RAW_STAGE`, then run `snowflake/02_load_bronze.sql`.
4. Run `snowflake/03_schedule.sql`. It deploys the dbt project from the `main` branch of this repo and schedules `dbt build` every day at 06:00. Re-run it after each merge to deploy the new code.

Steps 3 and 4 run as `MEDIRELAIS_PIPELINE`, never as `ACCOUNTADMIN`.

## Team

Atoui Soumaya 
Rahali Manel
Javaid Hadiqa 
