-- MédiRelais · bronze tables for the 4 sources (run by: python jobs/bootstrap_snowflake.py)
-- Bronze keeps the data exactly as received: text columns, raw JSON, no cleaning.
-- Every table carries _source / _source_file, _loaded_at and _batch_id (replay, debugging, freshness).
-- Safe to run again: everything is CREATE ... IF NOT EXISTS.

-- Run log: one row per job run (success or failure). The quality checks and the oral demo read it.
CREATE TABLE IF NOT EXISTS MEDIRELAIS.BRONZE.LOAD_RUNS (
    run_at TIMESTAMP_TZ, job VARCHAR, batch_id VARCHAR, status VARCHAR,
    rows_in NUMBER, rows_loaded NUMBER, message VARCHAR);

-- File formats ---------------------------------------------------------------------------
-- CSV with a header row, columns matched BY NAME (survives column order changes and renames)
CREATE FILE FORMAT IF NOT EXISTS MEDIRELAIS.BRONZE.FF_CSV_HEADER
    TYPE = CSV PARSE_HEADER = TRUE FIELD_OPTIONALLY_ENCLOSED_BY = '"'
    ERROR_ON_COLUMN_COUNT_MISMATCH = FALSE EMPTY_FIELD_AS_NULL = FALSE ENCODING = 'UTF8';
-- Tab-separated public files (BDPM): no header, no quotes
CREATE FILE FORMAT IF NOT EXISTS MEDIRELAIS.BRONZE.FF_TSV_RAW
    TYPE = CSV FIELD_DELIMITER = '\t' SKIP_HEADER = 0 FIELD_OPTIONALLY_ENCLOSED_BY = NONE
    ESCAPE_UNENCLOSED_FIELD = NONE ERROR_ON_COLUMN_COUNT_MISMATCH = FALSE ENCODING = 'UTF8';

-- S1 · Pharmacy stock database (Postgres) - incremental pull + MERGE --------------------
CREATE TABLE IF NOT EXISTS MEDIRELAIS.BRONZE.HOSPITALS_RAW (
    hospital_id VARCHAR, hospital_name VARCHAR, city VARCHAR, beds NUMBER,
    latitude NUMBER(7,3), longitude NUMBER(7,3), updated_at TIMESTAMP_TZ,
    _source VARCHAR, _loaded_at TIMESTAMP_TZ, _batch_id VARCHAR);
CREATE TABLE IF NOT EXISTS MEDIRELAIS.BRONZE.PRODUCTS_RAW (
    product_id VARCHAR, product_name VARCHAR, category VARCHAR, unit_cost_eur NUMBER(10,2),
    is_cold_chain BOOLEAN, is_narcotic BOOLEAN, match_keyword VARCHAR, updated_at TIMESTAMP_TZ,
    _source VARCHAR, _loaded_at TIMESTAMP_TZ, _batch_id VARCHAR);
CREATE TABLE IF NOT EXISTS MEDIRELAIS.BRONZE.STOCK_RAW (
    batch_id VARCHAR, hospital_id VARCHAR, product_id VARCHAR,
    qty_on_hand VARCHAR, expiry_date VARCHAR, is_recalled VARCHAR, updated_at TIMESTAMP_TZ,
    _source VARCHAR, _loaded_at TIMESTAMP_TZ, _batch_id VARCHAR);

-- S2 · Daily consumption files - batch COPY (columns matched by name: both names kept on drift)
CREATE TABLE IF NOT EXISTS MEDIRELAIS.BRONZE.CONSUMPTION_RAW (
    consumption_date VARCHAR, hospital_id VARCHAR, product_id VARCHAR,
    qty_used VARCHAR, quantity_used VARCHAR,
    _source_file VARCHAR, _file_row_number NUMBER, _loaded_at TIMESTAMP_TZ, _batch_id VARCHAR);

-- S3 · BDPM public drug database (real) - weekly full refresh, positional text columns
CREATE TABLE IF NOT EXISTS MEDIRELAIS.BRONZE.BDPM_SPECIALITES_RAW (
    c1 VARCHAR, c2 VARCHAR, c3 VARCHAR, c4 VARCHAR, c5 VARCHAR, c6 VARCHAR, c7 VARCHAR,
    c8 VARCHAR, c9 VARCHAR, c10 VARCHAR, c11 VARCHAR, c12 VARCHAR, c13 VARCHAR, c14 VARCHAR,
    _source_file VARCHAR, _loaded_at TIMESTAMP_TZ, _batch_id VARCHAR);
CREATE TABLE IF NOT EXISTS MEDIRELAIS.BRONZE.BDPM_PRESENTATIONS_RAW LIKE MEDIRELAIS.BRONZE.BDPM_SPECIALITES_RAW;
-- CIS_COMPO_bdpm.txt: the substances (molecules) of each medicine, used to match by molecule
CREATE TABLE IF NOT EXISTS MEDIRELAIS.BRONZE.BDPM_COMPOSITION_RAW LIKE MEDIRELAIS.BRONZE.BDPM_SPECIALITES_RAW;

-- S4 · BDPM shortages file (real) - daily pull, change detection by row hash + MERGE
CREATE TABLE IF NOT EXISTS MEDIRELAIS.BRONZE.SHORTAGES_RAW (
    c1 VARCHAR, c2 VARCHAR, c3 VARCHAR, c4 VARCHAR, c5 VARCHAR, c6 VARCHAR, c7 VARCHAR,
    c8 VARCHAR, c9 VARCHAR, c10 VARCHAR,
    row_hash VARCHAR, first_seen_at TIMESTAMP_TZ, last_seen_at TIMESTAMP_TZ, still_listed BOOLEAN,
    _source_file VARCHAR, _batch_id VARCHAR);

-- S5 (fridge sensors) and S6 (weather API) were removed on 2 Nov 2026: the project keeps
-- use cases 1 and 2 only. Their old tables (FRIDGE_READINGS_RAW, WEATHER_RAW) are no longer used.
