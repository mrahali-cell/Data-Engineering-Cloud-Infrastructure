-- Each product of the network linked to the national drug database (S3 BDPM) and to the
-- national shortage list (S4). Grain: one row per product.
--
-- Hospitals name medicines differently ("Doliprane 1g" here, "Paracetamol Biogaran 1000 mg"
-- there), so names are never compared between hospitals. Each product carries a
-- match_keyword (its active substance); BDPM medicines whose name contains that keyword as a
-- whole word are linked to it through their national CIS code.
-- Known limit: the match is on the substance only (not dose, form or brand names such as
-- Lantus for insulin glargine). The next step is the BDPM composition file (CIS_COMPO_bdpm.txt),
-- which lists the active substance of every CIS code.
WITH bdpm AS (
    SELECT
        TRIM(c1)  AS cis_code,
        TRIM(c2)  AS medicine_name,
        TRIM(c7)  AS marketing_status
    FROM {{ source('bronze', 'bdpm_specialites_raw') }}
    QUALIFY ROW_NUMBER() OVER (PARTITION BY TRIM(c1) ORDER BY _loaded_at DESC) = 1
),
matches AS (
    SELECT p.product_id, b.cis_code, b.medicine_name, b.marketing_status
    FROM {{ ref('silver_products') }} p
    JOIN bdpm b
      ON REGEXP_LIKE(UPPER(b.medicine_name), '(.*[^A-Z])?' || p.match_keyword || '([^A-Z].*)?')
),
-- S4: status 1 = out of stock, 2 = supply tension (3 = withdrawn, 4 = available again)
shortages AS (
    SELECT
        TRIM(c1)                         AS cis_code,
        TRIM(c3)                         AS status_code,
        TRIM(c4)                         AS status,
        TRY_TO_DATE(TRIM(c5), 'DD/MM/YYYY') AS shortage_since
    FROM {{ source('bronze', 'shortages_raw') }}
    WHERE still_listed
      AND TRIM(c3) IN ('1', '2')
)
SELECT
    p.product_id,
    p.product_name,
    p.match_keyword,
    COUNT(DISTINCT m.cis_code)                                          AS bdpm_medicines,
    COUNT(DISTINCT IFF(m.marketing_status ILIKE 'Commercialis%', m.cis_code, NULL)) AS bdpm_medicines_marketed,
    ANY_VALUE(m.medicine_name)                                          AS example_bdpm_name,
    COUNT(DISTINCT s.cis_code)                                          AS medicines_in_shortage,
    COUNT(DISTINCT s.cis_code) > 0                                      AS is_national_shortage,
    CASE WHEN COUNT_IF(s.status_code = '1') > 0 THEN 'out of stock'
         WHEN COUNT_IF(s.status_code = '2') > 0 THEN 'supply tension' END AS shortage_status,
    MIN(s.shortage_since)                                               AS shortage_since
FROM {{ ref('silver_products') }} p
LEFT JOIN matches m   ON m.product_id = p.product_id
LEFT JOIN shortages s ON s.cis_code   = m.cis_code
GROUP BY p.product_id, p.product_name, p.match_keyword
