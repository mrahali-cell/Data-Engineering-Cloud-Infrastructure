# Prompt for Claude Design: the MédiRelais oral-defense deck

Attach the files listed under "Attach" first, then paste everything below the line.

**Attach** (the more of these you can attach, the fewer empty frames you get back):
- The updated team deck, exported from Google Slides as .pptx: "Copy of MédiRelais – how it works and what is left". It has 40 slides and is the main source.
- `docs/MediRelais_Part4_Soumaya.pptx`.
- Diagrams: `docs/medirelais_pipeline.png` (the full pipeline) and `docs/terraform_architecture.png`.
- Incident proof: `docs/Incident 1/*.png` and `docs/Incident 2/*.png`.
- Source screenshots, from the `diagram-assets` branch, folder `docs/diagram-assets/`:
  - `bdpm-home.jpg` and `bdpm-download.jpg` (the government drug database);
  - `s1-stock-postgres-sample.png` and `s2-consumption-csv-sample.png`;
  - the tool logos (`logo-*.png`).
- Any screenshots you have of: the 3 dashboards, the Airflow DAG graph and grid, `terraform plan` (drift and "No changes"), the S3 state versions, the Snowflake access check, and the dbt lineage.

---

## Goal

Design a 16:9 deck for a 15–20 minute graded oral defense, plus a Q&A appendix. It's for **MédiRelais**, a data platform that moves medicines about to expire to the hospital that can use them in time. There is **no slide cap**: keep every slide that carries real content.

The audience is the course teacher, a Snowflake and cloud practitioner; the panel judges both business sense and technical depth. **Every slide must be understood in 5 seconds by a business person and survive a technical question.**

Start from the attached team deck: keep its story, numbers and level of detail. Redesign it to be visual and modern rather than copying its layouts.

## Three presenters, three parts

Each person answers alone on their own part, so every slide belongs to exactly one presenter.

| Part | Presenter | Slides (from the team deck) |
| --- | --- | --- |
| Opening | whole team | title, the problem, the 2 use cases and business model, the pipeline at a glance |
| 1 · Sources, ingestion and orchestration | **Manel** | all of Manel's slides, with **the same level of detail**: the 4 sources table, the simulator, one slide per source (S1 watermark + MERGE, S2 stage + COPY, S3 full refresh, S4 row hash), the shared job pattern, matching by molecule, before/after Airflow, Docker setup, how Airflow drives Snowflake, the 10-task DAG, DAG settings, the 2 checks, the green day-3 run. **Do not merge or cut these.** |
| 2 · Transformation, quality, incidents and dashboards | **Hadiqa** | silver cleaning and quarantine, gold's six numbers, the five transfer checks, how the receiver is chosen, the 5 transfers (€7,700), the dbt tests, **the 3 incidents**, the 3 dashboards |
| 3 · Platform, access and costs | **Soumaya** | Terraform (one repo, remote state, drift), who sees what, costs and the €470-per-€1 ratio |
| Close | whole team | status of the work, then Questions |
| Appendix | | Q&A on ingestion, Airflow, transformation, and Terraform/governance/costs |

**One move:** the incidents slide, currently in Manel's Airflow section, goes to Hadiqa's part. Manel keeps the two checks that stop the run; Hadiqa presents what happens when each incident is triggered. Incident 3 (source down) stays credited to Manel in the footer.

## Design system

- **Look:** modern, clean, generous white space. One idea per slide.
- **Colours:** the team deck's palette.
  - dark teal `#133A3E` for dividers and the title slide;
  - teal `#0B6E6E` as the accent;
  - light teal `#E1EFEF` for cards;
  - amber `#B5651D` only for warnings, incidents and "planned" items.
- **Titles:** keep the deck's convention, one sentence stating the takeaway. Shorten to at most 12 words where you can.
- **Body:** prefer a visual to bullets. Use at most about 30 words per slide, except tables, which keep their rows.
- **Logos:** the real tool logos (Snowflake, Airflow, dbt, Docker, Python, PostgreSQL, Terraform, AWS S3, Streamlit, GitHub), plus the République française logo for the government drug database.
- **Section dividers:** each part opens on a dark-teal divider naming its presenter, e.g. "Part 1 · Manel".
- **LIVE tag:** on every slide where the presenter switches to a live demo (Airflow DAG, incidents, dashboards, `terraform plan`, access check).
- **Footer:** one grey line naming the source (a file, a run or a date), as the team deck does.

## Visuals and screenshots: do your best, then leave a clean gap

Every content slide needs one main visual: a diagram, flow, chart, big number, screenshot or table. Work in this order:

1. **Use an attached screenshot or image** where one fits. Show it in a clean browser or laptop frame, cropped to what matters, with one highlighted callout.
2. **Draw it yourself** when it's a diagram, flow, timeline, chart or icon row. Examples:
   - the medallion flow;
   - the DAG chain;
   - the five transfer checks;
   - the showback bar chart (idle 55%, dashboards 37%, pipeline 6%, admin 1%);
   - the archive tiers (Standard › Glacier › Deep Archive).
3. **If you can't draw it on the slide**, generate it as a separate image (PNG or SVG), list it in your answer, and leave a frame on the slide named after it.
4. **If it's a screenshot of a tool you can't access** (Snowflake, Snowsight, Airflow, dbt, Terraform, AWS, Streamlit), never fake it. Leave an **empty, clearly labelled frame** of the right size and shape, for example "SCREENSHOT · Airflow DAG graph, run of day 3, all green". The presenter will paste it in.

Screenshots each part needs; use an attached one if it exists, otherwise leave a labelled frame:
- **Manel:** the Airflow DAG graph and grid; the `quality_gate` log at 5.8%; the `run_report` log with the 5 transfers; the `BRONZE.LOAD_RUNS` table; a Postgres/S1 sample; the BDPM website.
- **Hadiqa:**
  - a quarantine table in Snowflake;
  - a dbt test run;
  - incident 1: a red `quality_gate`, plus the dashboard keeping yesterday's figures;
  - incident 2: silver with 0 duplicates;
  - incident 3: red, then green after Clear;
  - the network dashboard (Business and Pipeline tabs) and the H01 hospital app.
- **Soumaya:** `terraform plan` showing the drift (`~ auto_suspend = 300 -> 60`), then "No changes"; the S3 state versions; the access check as H01 and as READER; the cost query result.

**Dashboards:** they run in Snowflake and need a login, so they can't be embedded. Show a screenshot frame with an **"Open live"** button linking to `[link to Snowflake app]`.

## Facts to use (from the team deck and the repo, current on 4 Nov 2026)

- **Business:**
  - 12 hospitals, about 6,500 beds;
  - €96M of medicines bought a year; ≈ €1.44M thrown away;
  - target: ≈ €576k saved a year;
  - revenue: a €1,500/month subscription per hospital (€216k a year), **subscription only**: French law forbids a fee or commission on redistributing medicines between hospitals;
  - the demo sample has 25 products, against about 2,500 in a real pharmacy.
- **Manel:** keep every number on his slides: 62 rows; 315 lines; 69,187 rows; 706 read, 0 new; gate 22 / 377 = 5.8%; 10 tasks in 7 steps; retries; the settings table.
- **Hadiqa:**
  - stock: 455 clean, 35 quarantined; consumption: 26,148 clean, 2,589 quarantined;
  - six gold numbers;
  - the five checks;
  - 5 transfers worth ≈ €7,700, with heparin from H09 to H04 first;
  - dbt tests: transfer rules, planted acceptance cases, quarantine under 15%, accepted ranges, all 12 hospitals reporting, consumption from every hospital, 8 weeks of history for days of cover, shortages ranked first;
  - incident 1: gate red at ≈ 45%, gold not refreshed;
  - incident 2: everything green, 0 duplicates in silver;
  - incident 3: retried twice, then red; green after Clear;
  - 3 dashboards: the network dashboard (Business and Pipeline tabs, data-quality tile) and one app per pharmacist (H01, H04), each showing only its own hospital, with results reused for 1 hour.
- **Soumaya:**
  - Terraform 1.17.1, providers pinned; state in S3, versioned, encrypted and locked;
  - a key-only service user with SYSADMIN and SECURITYADMIN, never ACCOUNTADMIN;
  - drift demo: 300 → 60, then "No changes";
  - who sees what: pharmacists see their own hospital with no prices; Finance sees prices (max €1,150); readers read GOLD only;
  - costs: €16.35 over 30 days; idle 55%, dashboards 37%, pipeline 6%; €0.14 per dbt build (≈ €4 a month); a 10-credit monthly cap (≈ €33);
  - ratio: ≈ €470 saved per €1 of platform. Footnote: $3.90 per credit; €/$ 0.86 assumed; measured 3 Nov 2026.

## Rules

- **Use only these numbers or the attached decks'. Invent nothing.** Leave a visible `[number]` placeholder for a missing figure.
- **Show these as "planned", never as done:**
  - the nightly archive copy as an Airflow step;
  - the AWS budget alert;
  - e-mail alerts from Airflow.
- **Never mention anything removed:**
  - Google Cloud or GCS (we use AWS);
  - fridge sensors and weather (use case 3, removed on 2 Nov);
  - any success fee.
- **Keep identifiers off the slides:** no account IDs, full bucket names, keys or passwords.
- **Speaker notes on every slide:** the presenter's name, a target time, and 2–3 sentences to say out loud, one of which links the slide to the business. The times must add up to 18–20 minutes, so Manel's detailed slides get about 30–45 seconds each.

## Output

1. The deck, exportable as .pptx and PDF.
2. **A gap list:** every empty screenshot frame and every visual you generated as a separate image, each with its slide number and exact label, so the presenters can fill them in.
3. Every remaining `[number]` or `[link]` placeholder.
