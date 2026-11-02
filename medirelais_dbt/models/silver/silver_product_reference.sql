-- Each product of the network linked to the national drug database (S3 BDPM) and to the
-- national shortage list (S4). Grain: one row per product.
--
-- Hospitals and brands name medicines differently ("Doliprane 1000 mg" and "Paracétamol
-- Biogaran 1000 mg" are the same molecule), so we match on the MOLECULE, not on the name.
-- Each product carries a match_keyword (its active substance, e.g. PARACETAMOL). A BDPM medicine
-- (one national CIS code) is linked to the product when:
--   1. by molecule: the composition file (CIS_COMPO_bdpm.txt) lists that substance as the
--      medicine's ONLY active substance -> finds brand names (Doliprane, Lantus...).
--      Only single-substance medicines, so a paracetamol + codeine combination is not counted
--      as paracetamol.
--   2. by name: the medicine's name contains the substance (generics: "PARACETAMOL BIOGARAN").
-- Both sides are compared in upper case without accents (PARACÉTAMOL = PARACETAMOL).
-- Known limit: the dose and the form are not compared (500 mg and 1 g count as the same product).
WITH bdpm AS (
    SELECT
        TRIM(c1)  AS cis_code,
        TRIM(c2)  AS medicine_name,
        TRIM(c7)  AS marketing_status
    FROM {{ source('bronze', 'bdpm_specialites_raw') }}
    QUALIFY ROW_NUMBER() OVER (PARTITION BY TRIM(c1) ORDER BY _loaded_at DESC) = 1
),
-- CIS_COMPO_bdpm.txt: c1 CIS code, c4 substance name, c7 nature (SA = active substance,
-- FT = therapeutic fraction of an active substance)
active_substances AS (
    SELECT DISTINCT
        TRIM(c1) AS cis_code,
        TRIM(c4) AS substance_name
    FROM {{ source('bronze', 'bdpm_composition_raw') }}
    WHERE TRIM(c7) = 'SA'
),
single_substance AS (
    SELECT cis_code, ANY_VALUE(substance_name) AS substance_name
    FROM active_substances
    GROUP BY cis_code
    HAVING COUNT(*) = 1
),
by_molecule AS (
    SELECT p.product_id, m.cis_code
    FROM {{ ref('silver_products') }} p
    JOIN single_substance m
      ON {{ contains_word('m.substance_name', 'p.match_keyword') }}
),
by_name AS (
    SELECT p.product_id, b.cis_code
    FROM {{ ref('silver_products') }} p
    JOIN bdpm b
      ON {{ contains_word('b.medicine_name', 'p.match_keyword') }}
),
matches AS (
    SELECT
        COALESCE(mo.product_id, na.product_id) AS product_id,
        COALESCE(mo.cis_code, na.cis_code)     AS cis_code,
        mo.cis_code IS NOT NULL                AS found_by_molecule,
        na.cis_code IS NOT NULL                AS found_by_name
    FROM by_molecule mo
    FULL OUTER JOIN by_name na
      ON na.product_id = mo.product_id
     AND na.cis_code   = mo.cis_code
),
matched_medicines AS (
    SELECT m.*, b.medicine_name, b.marketing_status
    FROM matches m
    JOIN bdpm b ON b.cis_code = m.cis_code
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
    COUNT(DISTINCT IFF(m.found_by_molecule AND NOT m.found_by_name, m.cis_code, NULL))
                                                                        AS bdpm_medicines_found_only_by_molecule,
    COUNT(DISTINCT IFF(m.marketing_status ILIKE 'Commercialis%', m.cis_code, NULL)) AS bdpm_medicines_marketed,
    ANY_VALUE(m.medicine_name)                                          AS example_bdpm_name,
    MAX(IFF(m.found_by_molecule AND NOT m.found_by_name, m.medicine_name, NULL))
                                                                        AS example_brand_name,
    COUNT(DISTINCT s.cis_code)                                          AS medicines_in_shortage,
    COUNT(DISTINCT s.cis_code) > 0                                      AS is_national_shortage,
    CASE WHEN COUNT_IF(s.status_code = '1') > 0 THEN 'out of stock'
         WHEN COUNT_IF(s.status_code = '2') > 0 THEN 'supply tension' END AS shortage_status,
    MIN(s.shortage_since)                                               AS shortage_since
FROM {{ ref('silver_products') }} p
LEFT JOIN matched_medicines m ON m.product_id = p.product_id
LEFT JOIN shortages s         ON s.cis_code   = m.cis_code
GROUP BY p.product_id, p.product_name, p.match_keyword
