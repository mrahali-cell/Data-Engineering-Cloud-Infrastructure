# Prompt: build Part 4 of the MédiRelais oral-defense deck (Soumaya)

Copy everything below the line into Claude (or another assistant that can create PowerPoint / Google Slides
and, ideally, read Granola and Google Drive). Attach the images listed in <assets> if the tool cannot read
local files.

---

<role>
You are a senior data-platform consultant and presentation designer. You are building the slides for one
student's segment of a graded oral defense in a Master's course, "Data Engineering & Cloud Infrastructure"
(MSA-DAT09-02, Albert School, November 2026). The audience is the course teacher, who is a Snowflake and
cloud practitioner and will question each student alone on their own part. Every slide must be technically
exact, defensible under questioning, and tied to the business case.
</role>

<goal>
Create "Part 4 · Soumaya: platform as code, governance and costs" of the MédiRelais deck: 8 main slides
plus a short Q&A appendix, in the same style as the team deck, as a 16:9 PowerPoint (.pptx) with speaker
notes on every slide. These slides will be inserted after "Part 3 · Team" in the existing team deck, so
they must look like they belong to it.
</goal>

<sources_to_read_first>
Read these before writing anything. They are the ground truth; the facts block below summarises them.

1. Team deck (style and story to match): Google Slides "MédiRelais – how it works and what is left (team
   meeting, 2 Nov)", https://docs.google.com/presentation/d/164zqEaq9MzpQiA3e0bt9vzZa90Cixs3c4uw5xzzhO8c
2. Course recordings in Granola (what the teacher taught and will expect):
   - Oct 21, 2026: project brief, deliverables, RBAC, resource monitors.
     https://notes.granola.ai/d/be2d1a5f-11ff-4ed3-bd0b-5f6f3a9c79be
   - Oct 30, 2026: Terraform / IaC (plan, apply, remote state with locking, drift) and the oral-defense
     requirements (governance shown live: masking, access control, data ownership; everything in the
     architecture must run live; link every choice to the business).
     https://notes.granola.ai/d/e0c8f58e-8634-4ad9-aaeb-fa573b1763b6
   - Nov 2, 2026: FinOps (visibility, control, optimization; compute, storage, data transfer; tags and
     query tags; showback before chargeback; idle warehouses; total cost of ownership; Glacier tiers).
     https://notes.granola.ai/d/c4fbfbd1-983c-45de-b9b9-2868b63a4d96
   Use the teacher's own vocabulary on the slides (the three FinOps pillars, "idle", "drift", "remote
   state", "showback", "workload isolation", "TCO").
3. The team's checklist: Google Doc "MédiRelais oral defense checklist",
   https://docs.google.com/document/d/1ypll5v6VvvRyeDV_YbZWtYhiEhtW0xhxgUoGV2TxBVs
4. The GitHub repo, if you can read it: terraform/ (all .tf files and README.md), snowflake/04_access_check.sql,
   snowflake/05_costs.sql, medirelais_dbt/dbt_project.yml, docs/terraform_architecture.png.

If a source contradicts the facts block, trust the facts block for Soumaya's part (it is newer) and list the
contradiction at the end of your answer.
</sources_to_read_first>

<project_context>
MédiRelais connects the pharmacies of 12 hospitals (one group in Île-de-France) and suggests, every morning,
transfers of medicines about to expire to the hospital that can use them in time. Team: Manel Rahali
(sources, ingestion, Airflow), Hadiqa Javaid (silver/gold with dbt, tests, incidents, dashboard), Soumaya
Atoui (Terraform, governance, costs). Stack: 4 sources, Python ingestion in Docker, Airflow DAG at 06:00,
Snowflake on AWS Paris (eu-west-3) with bronze/silver/gold built by dbt, Streamlit dashboard in Snowflake.
Grading: /80 on a C1–C8 matrix, 35% of the course grade; Soumaya's part maps to C5 (infrastructure as code)
and C7 (governance and costs). The whole oral is 15–20 minutes for three people, so this part gets about
5–6 minutes: one idea per slide.
</project_context>

<facts>
Use only these numbers and claims. Do not invent figures, percentages or features.

## A. Terraform (C5)
- Terraform 1.17.1, providers snowflakedb/snowflake 2.22.1 and hashicorp/aws 6.71.0, all pinned.
- One repo controls two platforms: Snowflake (objects, roles, access rules) and Soumaya's own AWS account
  (archive storage, IAM).
- Remote state in S3 bucket medirelais-tfstate-… (AWS eu-north-1): private, versioned (59 versions at the
  time of the screenshot), encrypted, locked during a run (use_lockfile), so two people cannot apply at once.
- Terraform signs in as a service user TERRAFORM with an RSA key pair, no password. It uses SYSADMIN for
  objects and SECURITYADMIN for roles and grants, never ACCOUNTADMIN (least privilege). The key is
  gitignored; a scan of all 45 commits found no secret.
- Files: platform.tf (warehouse MEDIRELAIS_WH, database MEDIRELAIS, schemas BRONZE/SILVER/GOLD, pipeline
  role), roles.tf, governance.tf, archive.tf, costs.tf, imports.tf, plus bootstrap.sql for the one-time
  manual steps.
- The objects first created by hand were taken over with import blocks, without recreating them. The
  database and schemas have prevent_destroy: a plan that would drop them (and every table) is refused.
- Deliberately not in Terraform: tables (dbt owns silver/gold, ingestion owns bronze; they change daily),
  the dbt project / task / dashboard (deployed from Git by snowflake/03_schedule.sql), the accounts and the
  TERRAFORM user itself (need ACCOUNTADMIN).
- Workflow: init once, then plan → read the plan → apply → plan again must say "No changes".
- Drift demo (done, 4 screenshots): (1) plan = No changes; (2) someone sets the warehouse auto-suspend to
  300 s by hand in Snowsight, plan shows `~ auto_suspend = 300 -> 60`, "1 to change"; (3) apply, typed yes;
  (4) plan = No changes again. A second real case: attaching the resource monitor by hand also showed up
  as drift, so it was declared in platform.tf.
- Archive (archive.tf): S3 bucket medirelais-archive-… with public access blocked, AES256 encryption, and a
  lifecycle rule: S3 Standard for 90 days, then Glacier, then Deep Archive after 1 year. Snowflake writes to
  it through the external stage BRONZE.ARCHIVE_STAGE, as Parquet, one folder per day
  (consumption_raw/dt=YYYY-MM-DD/). Example: the daily consumption rows of each hospital, kept for replay
  after an incident and for audit.
- Archive access today: an IAM user allowed on this bucket only; Terraform creates its key and hands it to
  the stage (never typed, only in the encrypted state). Target, already coded: no key, Snowflake assumes an
  IAM role through a storage integration. The AWS Free plan's guardrails block that role today; after an
  upgrade, one variable switches it.
- Regions: Snowflake runs in Paris on Snowflake's own AWS; Soumaya's AWS account only allows eu-north-1
  (Stockholm) on the Free plan. Both are in the EU.
- Status to state honestly: the nightly archive COPY is written and tested once, but is not yet wired into
  the Airflow DAG [confirm current status before presenting].
- Diagram ready: docs/terraform_architecture.png (Excalidraw style; editable .excalidraw next to it).

## B. Governance (C7)
- No patient or personal data: stock and consumption by hospital and product only.
- Data owners (stewards): Manel for sources and bronze, Hadiqa for silver and gold, Soumaya for access
  rules, platform, archive and costs. Account administrators: Soumaya and Hadiqa.
- Who sees what in GOLD, enforced by Snowflake itself, not by the dashboard:

  | Role | Rows | Purchase price (unit_cost_eur) |
  | --- | --- | --- |
  | MEDIRELAIS_PIPELINE (builds the tables) | all | visible |
  | MEDIRELAIS_FINANCE | all | visible |
  | MEDIRELAIS_READER (the network dashboard) | all | hidden (NULL) |
  | MEDIRELAIS_PHARMACIST_H01 / _H04 | own hospital only | hidden |
  | SYSADMIN / ACCOUNTADMIN (platform admins) | all | hidden |

- Reader roles read GOLD only; READER querying BRONZE is refused ("does not exist or not authorized").
- Row access policies: HOSPITAL_ROWS (value at risk, days of cover) and TRANSFER_ROWS (transfer
  suggestions: a pharmacist sees what their hospital sends or receives). Both read a mapping table
  GOVERNANCE.HOSPITAL_ACCESS generated from a Terraform map: adding a hospital = one line + one role.
- Masking policy PURCHASE_PRICE: negotiated prices visible to FINANCE and PIPELINE only.
- The rules live in Terraform; dbt only re-attaches them after each daily rebuild (post-hooks), and the
  pipeline role has APPLY but cannot rewrite them (separation of duties).
- The policies check CURRENT_ROLE(): Snowsight turns all secondary roles on by default, which would let an
  admin testing as a pharmacist still see every hospital.
- The dashboard is created by READER (a Streamlit app runs with its owner's rights), so it shows every
  hospital and no prices.
- Verified live with snowflake/04_access_check.sql: H01 sees only H01 (1 row, price NULL); H04 sees its own
  rows and the transfer H09 → H04; READER sees all 21 batches with prices NULL; FINANCE sees prices (max
  €1,150); READER on BRONZE is refused. Audit: ACCESS_HISTORY joined to QUERY_HISTORY lists who read which
  gold table with which role (257 reads over 7 days at the time of the check).

## C. Costs / FinOps (C7). Measured on 3 Nov 2026 with snowflake/05_costs.sql
- Price per credit: $3.90 (read from Snowflake's own rate sheet). Euro figures use 0.86 €/$ (an assumption;
  say so in a footnote).
- Last 30 days: €16.35 (about 4.9 credits), almost all warehouse compute, and mostly the cost of building
  the project.
- Showback, warehouse compute over 30 days (≈5.7 credits): idle, warehouse running with no query: 55%
  (€10.63); dashboard: 37% (€7.18), tagged automatically by Snowflake's Streamlit; pipeline: 6% (€1.08);
  admin work: 1% (€0.20).
- One dbt build: 25–40 s, about 0.04 credits billed ≈ €0.14 (measured on the Snowflake task runs of 31 Oct
  and 1 Nov, before Airflow took over the schedule). Daily: about €4 a month.
- Storage: the MEDIRELAIS database holds 57 MB ≈ €0.001 a month.
- Data transfer: the archive COPY moved 0.09 MB from Paris (eu-west-3) to Stockholm (eu-north-1). That is a
  cross-region transfer, which is billed: tiny today, and the fix is to move the bucket to Paris once the AWS
  plan allows it.
- Business ratio: on the latest snapshot the suggested transfers can save €7,700 of medicine (5 transfers,
  out of €38,474 at risk), against €16.35 of platform cost over 30 days: about €470 saved per €1 spent.
  Say clearly that the €7,700 is one day's snapshot and the €16.35 is 30 days, mostly development.
- Visibility (done): COST_CENTER tag on the warehouse and the database (Terraform, costs.tf); dbt query tag
  "medirelais:pipeline:dbt"; Streamlit queries tagged automatically; AWS resources tagged project=medirelais,
  managed_by=terraform; showback by role, since roles map to teams.
- Control (done): resource monitor MEDIRELAIS_MONITOR, 10 credits a month (≈ €33): email at 75%, no new
  queries at 90%, everything stopped at 100%, reset monthly, declared in Terraform. Auto-suspend after 60 s
  idle (enforced, see drift demo). AWS $1 budget alert: [confirm it was created before presenting].
- Optimization (done): query acceleration switched off via Terraform (it rents extra compute for big scans;
  our tables are small); XSMALL warehouse is right-sized; dashboard results cached for 1 hour (gold changes
  once a day); cold data goes to Glacier and Deep Archive.
- Next steps (not built; present as recommendations): a separate small warehouse for the dashboard
  (workload isolation, so its cost and idle time are separate); start with showback, move to chargeback per
  team later; count Airflow's maintenance time in its TCO (open source is free to license, not to run);
  after the course, suspend the warehouse, delete the archive key and the buckets (the database's
  prevent_destroy has to be lifted on purpose).
- Status to state honestly: the dbt query tag and the dashboard cache go live after the next commit and
  redeploy [confirm before presenting].
</facts>

<assets>
- docs/terraform_architecture.png: Terraform → Snowflake and AWS diagram. Use it on the first Terraform slide.
- Drift demo screenshots 1–4 (Soumaya's files).
- Screenshot of the state bucket's 59 versions in S3.
- dbt lineage screenshot (22 nodes), optional.
If an image is not available to you, put a clearly labelled grey placeholder box ("[Screenshot: plan
showing ~ auto_suspend = 300 -> 60]") of the right size, never a fake image.
</assets>

<slide_plan>
Main slides (each title is a full-sentence takeaway, as in the team deck):

0. Section divider, "Part 4 · Soumaya". Subtitle: "Platform as code, governance and costs: who can
   change the platform, who sees which data, and what it costs".
1. "One repo controls Snowflake and AWS, and its state lives in S3". The architecture diagram, plus
   3 short callouts: remote state (versioned, encrypted, locked), least privilege (SYSADMIN / SECURITYADMIN,
   never ACCOUNTADMIN), and what is not in Terraform and why.
2. "A change made by hand is caught by the next plan". The drift demo as 4 steps with screenshots
   (plan → hand edit → drift shown → apply → No changes). Marked LIVE DEMO. Footer: imports took over
   existing objects without recreating them; prevent_destroy protects the data.
3. "Old raw data leaves Snowflake for cheap S3 tiers". Timeline Standard 0–90 days → Glacier → Deep
   Archive after 1 year; what is archived (daily consumption, Parquet, one folder per day) and why
   (replay, audit); IAM user today vs keyless role target; Paris → Stockholm flagged as a known cost and
   region trade-off.
4. "Each role sees only what its job needs, enforced by Snowflake". The who-sees-what table, "no patient
   data", and the data owners.
5. "The rules live in Terraform and survive every daily rebuild". Flow: Terraform defines the policies →
   dbt rebuilds gold → post-hooks re-attach → each role queries. Callouts: CURRENT_ROLE vs secondary
   roles, dashboard created by READER, audit with ACCESS_HISTORY. Marked LIVE DEMO
   (04_access_check.sql: H01, H04, READER, FINANCE, READER on BRONZE refused).
6. "FinOps on MédiRelais: see it, cap it, then optimise it". Three columns (visibility / control /
   optimization) with what was done in each.
7. "The platform costs €16 a month to build and about €4 a month to run". Showback bar chart (idle 55%,
   dashboard 37%, pipeline 6%, admin 1%), cost per dbt run, storage, and the cross-region transfer flag.
   Footnote with the price per credit, exchange rate and date.
8. "Every euro of platform saves about €470 of medicine". The business ratio with its honest caveat, and
   the 3–4 next steps (dashboard warehouse, chargeback later, TCO, shutdown plan).

Appendix (after the team's existing Q&A slides), "Q&A on Terraform, governance and costs": a
two-column table (question / short answer, max 20 words each) with 10–12 questions the teacher is likely
to ask, for example: why Terraform if Snowflake is SaaS; why remote state and locking; what is in the state
file and how it is protected; why not ACCOUNTADMIN; why tables are not in Terraform; Terraform vs OpenTofu;
why Stockholm when Snowflake is in Paris; why an IAM key and not a role; does masking reduce cost (no, the
query still runs in full); what happens at 100% of the quota (the pipeline stops: a deliberate trade-off);
why 55% idle and how to fix it; showback vs chargeback.
</slide_plan>

<style>
Match the team deck exactly:
- Titles are one full sentence stating the conclusion, in sentence case, no full stop.
- Body: short phrases, at most 5 bullets or one table / one diagram per slide; no paragraph over 2 lines.
- Flows are written as boxes joined by "›", as in the team deck's pipeline slides.
- A small grey footer line on most slides giving the source: file names (e.g. terraform/governance.tf),
  the date of the measurement, or the assumption used.
- Use the deck's existing colours and fonts. If you cannot read them: dark navy titles, one teal accent
  colour, light grey footers, plenty of white space.
- Charts: one simple horizontal bar chart for the showback, labelled with values; no 3D, no pie charts.
- Plain, precise English. No marketing words ("seamless", "robust", "cutting-edge"). Do not use the word
  "simply".
- Speaker notes: 60–100 words per slide, written as what Soumaya says out loud, first person, including
  the one sentence that links the slide to the business (pharmacists, hospitals, money saved).
</style>

<rules>
- Never state as done something the facts block marks [confirm] or as a next step; show those as
  "planned" or leave them out.
- Do not put secrets, keys, passwords, account locators or full bucket names on the slides; "medirelais-
  tfstate-…" is enough.
- Every number on a slide must appear in the facts block, with its unit and period.
- Keep Soumaya's part about her own work; refer to Manel's and Hadiqa's parts only to connect the story
  (e.g. "the dashboard Hadiqa built is created by READER").
- If the team deck says the Terraform state is on GCP, that is outdated: it is on AWS S3.
</rules>

<output>
1. The .pptx file (or the slides added to a copy of the team deck if you can edit Google Slides).
2. Below it, a short list: each slide's title, the assets it needs, and every [confirm] item Soumaya must
   check before presenting.
3. Any contradiction you found between the sources and the facts block.
Before delivering, check every slide against the rules above and fix anything that breaks them.
</output>
