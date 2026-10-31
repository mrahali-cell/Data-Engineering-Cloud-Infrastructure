-- MédiRelais · Step 2: load the CSV files (uploaded to RAW_STAGE) into bronze
-- Safe to re-run: COPY INTO skips files it has already loaded.
USE ROLE MEDIRELAIS_PIPELINE;
USE WAREHOUSE MEDIRELAIS_WH;

-- Each row keeps the file it came from (_source) and that file's checksum
-- (_batch_id); _loaded_at is filled in by the table default.
COPY INTO MEDIRELAIS.BRONZE.HOSPITALS (hospital_id, hospital_name, city, beds, _source, _batch_id)
  FROM (SELECT $1, $2, $3, $4, METADATA$FILENAME, METADATA$FILE_CONTENT_KEY
        FROM @MEDIRELAIS.BRONZE.RAW_STAGE/hospitals.csv);
COPY INTO MEDIRELAIS.BRONZE.PRODUCTS (product_id, product_name, category, unit_cost_eur,
                                      is_cold_chain, is_narcotic, _source, _batch_id)
  FROM (SELECT $1, $2, $3, $4, $5, $6, METADATA$FILENAME, METADATA$FILE_CONTENT_KEY
        FROM @MEDIRELAIS.BRONZE.RAW_STAGE/products.csv);
COPY INTO MEDIRELAIS.BRONZE.STOCK (snapshot_date, hospital_id, product_id, batch_id,
                                   qty_on_hand, expiry_date, is_recalled, _source, _batch_id)
  FROM (SELECT $1, $2, $3, $4, $5, $6, $7, METADATA$FILENAME, METADATA$FILE_CONTENT_KEY
        FROM @MEDIRELAIS.BRONZE.RAW_STAGE/stock.csv);
COPY INTO MEDIRELAIS.BRONZE.CONSUMPTION (consumption_date, hospital_id, product_id, qty_used,
                                         _source, _batch_id)
  FROM (SELECT $1, $2, $3, $4, METADATA$FILENAME, METADATA$FILE_CONTENT_KEY
        FROM @MEDIRELAIS.BRONZE.RAW_STAGE/consumption.csv);

-- Check: expected 12 / 25 / 464 / 26945
SELECT 'hospitals' AS table_name, COUNT(*) AS row_count FROM MEDIRELAIS.BRONZE.HOSPITALS
UNION ALL SELECT 'products', COUNT(*) FROM MEDIRELAIS.BRONZE.PRODUCTS
UNION ALL SELECT 'stock', COUNT(*) FROM MEDIRELAIS.BRONZE.STOCK
UNION ALL SELECT 'consumption', COUNT(*) FROM MEDIRELAIS.BRONZE.CONSUMPTION;
