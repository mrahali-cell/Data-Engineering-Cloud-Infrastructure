-- README: the network is "12 hospitals of one hospital group".
-- The test FAILS if this query returns a row.
SELECT COUNT(*) AS hospitals
FROM {{ ref('silver_hospitals') }}
HAVING COUNT(*) <> 12
