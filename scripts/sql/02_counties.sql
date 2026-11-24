-- One row per county: crashes per 1,000 residents, deer share,
-- change from last year, and statewide ranks.
WITH cur AS (
  SELECT c.county, c.county_code, c.total, c.interstate, c.us_route,
         c.state_route, c.local_street, d.deer_crashes AS deer
    FROM county_crashes c
    JOIN deer_crashes d ON d.county = c.county AND d.year = c.year
   WHERE c.year = :year
),
prev AS (
  SELECT c.county, c.total, d.deer_crashes AS deer
    FROM county_crashes c
    JOIN deer_crashes d ON d.county = c.county AND d.year = c.year
   WHERE c.year = :year - 1
),
joined AS (
  SELECT cur.*, p.population,
         prev.total AS total_prev, prev.deer AS deer_prev,
         1000.0 * cur.total / p.population AS per_1k,
         1000.0 * cur.deer  / p.population AS deer_per_1k,
         100.0  * cur.deer  / cur.total    AS deer_share,
         100.0  * (cur.total - prev.total) / prev.total AS change_pct,
         100.0  * cur.interstate / cur.total AS interstate_share
    FROM cur
    JOIN prev USING (county)
    JOIN population p USING (county)
)
SELECT county, county_code, population, total, total_prev, deer, deer_prev,
       ROUND(per_1k, 2)           AS per_1k,
       ROUND(deer_per_1k, 2)      AS deer_per_1k,
       ROUND(deer_share, 1)       AS deer_share,
       ROUND(change_pct, 1)       AS change_pct,
       ROUND(interstate_share, 1) AS interstate_share,
       interstate, us_route, state_route, local_street,
       RANK() OVER (ORDER BY total DESC)      AS rank_total,
       RANK() OVER (ORDER BY per_1k DESC)     AS rank_per_1k,
       RANK() OVER (ORDER BY deer DESC)       AS rank_deer,
       RANK() OVER (ORDER BY deer_share DESC) AS rank_deer_share
  FROM joined
 ORDER BY county;
