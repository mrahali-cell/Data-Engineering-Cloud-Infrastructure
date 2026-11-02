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
| Each member hospital | Success fee on medication saved from expiry | 10% of value saved | ≈ €58,000 |
| **Total revenue** | | | **≈ €274,000** |

The success fee aligns MédiRelais with the hospitals: it earns more only when less medication is thrown away.

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
- **Value saved**, the base of the 10% success fee, counts the units that were actually transferred and used before expiry. It needs a register of real transfers, which is out of scope for this project. Saveable value is its forecast.

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
ingestion/           4 sources -> bronze: source simulator, one job per source, Dockerfile, docker-compose
medirelais_dbt/      dbt project: silver (cleaning, quarantine) and gold (metrics), tests
snowflake/           setup and scheduling scripts
streamlit/           dashboard
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

## 4. How to run

**Ingestion (4 sources → bronze)**, with Docker Desktop running. Details in [`ingestion/README.md`](ingestion/README.md).

```bash
cd ingestion
cp .env.example .env                        # SNOWFLAKE_USER = your LOGIN_NAME
docker compose run --rm keygen              # prints the ALTER USER line to run once in Snowflake
docker compose up -d pharmacy-db
docker compose run --rm ingest python run_all.py --day 1    # then --day 2, 3...
```

**First CSV version** (kept until silver is moved to the new bronze tables):

1. `python generate_data.py` writes the CSV files to `data/`.
2. An admin runs `snowflake/01_setup.sql` once. It creates the warehouse, the database, the bronze tables, the `MEDIRELAIS_PIPELINE` role and the link to this GitHub repo.
3. Upload the CSV files to `@MEDIRELAIS.BRONZE.RAW_STAGE`, then run `snowflake/02_load_bronze.sql`.
4. Run `snowflake/03_schedule.sql`. It deploys the dbt project from the `main` branch of this repo and schedules `dbt build` every day at 06:00. Re-run it after each merge to deploy the new code.

Steps 3 and 4 run as `MEDIRELAIS_PIPELINE`, never as `ACCOUNTADMIN`.

**Upgrading an account set up before 1 Nov 2026.** The old bronze tables were typed and have no `_source`, `_loaded_at` or `_batch_id`, and the files were regenerated. Once, before step 3:

```sql
USE ROLE SYSADMIN;
DROP TABLE MEDIRELAIS.BRONZE.HOSPITALS;   -- bronze is rebuilt from the files in the stage
DROP TABLE MEDIRELAIS.BRONZE.PRODUCTS;
DROP TABLE MEDIRELAIS.BRONZE.STOCK;
DROP TABLE MEDIRELAIS.BRONZE.CONSUMPTION;
-- then re-run 01_setup.sql, and upload the new CSV files with PUT ... OVERWRITE = TRUE
```

## Team

Atoui Soumaya 
Rahali Manel
Javaid Hadiqa 
