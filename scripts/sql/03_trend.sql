-- Statewide crashes by year, with the change from the year before
-- and the crash rate per 100 million miles driven (where miles are known).
SELECT year,
       crashes,
       crashes - LAG(crashes) OVER (ORDER BY year) AS change,
       ROUND(100.0 * (crashes - LAG(crashes) OVER (ORDER BY year))
             / LAG(crashes) OVER (ORDER BY year), 1) AS change_pct,
       vmt_billions,
       ROUND(crashes / (vmt_billions * 10.0), 1) AS per_100m_miles,
       ROUND(1000.0 * crashes / (registered_vehicles_millions * 1e6), 1) AS per_1k_vehicles
  FROM statewide_by_year
 ORDER BY year;
