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
- **Data:** each hospital pharmacy sends a nightly stock extract from its pharmacy system, plus daily consumption and orders. Fridges send temperature readings every 5 minutes.
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
- Cold-chain products must prove they stayed between **2 °C and 8 °C** the whole time.
- Narcotics and recalled batches are **never** transferred.
- Transfers stay **inside the hospital group**, under a pharmacist's responsibility.
- **No patient data** is used: only stock, orders and consumption.

---

## 2. Use cases and business value

Two use cases carry the business case:
- the first saves medication that is about to expire;
- the second stops hospitals from over-ordering in the first place.

A third use case, cold-chain proof, is optional and adds a real-time sensor source.

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
- **Exclusions:** narcotics, recalled batches, batches already reserved for a transfer, batches already expired.

**Metric 2 · Value saved:** the base of the success fee.

```
value_saved = SUM(qty_transferred × unit_cost)
              counting only units consumed by the receiving hospital before expiry
```

- **Grain:** one row per transfer × month.
- **Exclusions:** transfers that were cancelled or returned.

**Acceptance test**, on a fixed test dataset of 50 batches:
- the expiry list matches a hand-checked list exactly;
- total value at risk matches the manual calculation to the cent;
- no suggested transfer has fewer than 30 days left or a value under €200.

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
- **Exclusions:** products with less than 8 weeks of history, and products with zero consumption.
- **Alert:** when days of cover is longer than the remaining shelf life, the stock will expire before it is used.

**Acceptance test:**
- for 3 sample products, the computed cover equals a manual calculation;
- a product deliberately over-stocked in the test data is flagged.

### Use case 3 (optional) · Cold-chain proof

| | |
| --- | --- |
| **Decision** | Can this fridge batch be transferred safely? |
| **User** | The hospital pharmacist |
| **Metric** | Share of time a fridge stayed between 2 °C and 8 °C per day (grain: fridge × day; gaps under 10 minutes ignored) |
| **Frequency** | Every 15 minutes, since a fridge failure must be caught the same day |
| **Acceptance test** | A temperature spike injected into the test data blocks the transfer of that fridge's batches |

---

## 3. Architecture

*Coming next: data sources → ingestion → bronze / silver / gold → dashboards.*

## 4. How to run

*Coming next.*

## Team

*Names here.*
