-- Share of each day's crashes in each 3-hour window: all crashes vs. deer crashes.
-- Latest year, plus the five-year average share for comparison.
WITH shares AS (
  SELECT year, bin, label,
         all_crashes, deer_crashes,
         100.0 * all_crashes  / SUM(all_crashes)  OVER (PARTITION BY year) AS all_share,
         100.0 * deer_crashes / SUM(deer_crashes) OVER (PARTITION BY year) AS deer_share
    FROM time_of_day
   WHERE label <> 'Unknown'
)
SELECT bin, label,
       MAX(CASE WHEN year = :year THEN all_crashes END)  AS all_crashes,
       MAX(CASE WHEN year = :year THEN deer_crashes END) AS deer_crashes,
       ROUND(MAX(CASE WHEN year = :year THEN all_share END), 1)  AS all_share,
       ROUND(MAX(CASE WHEN year = :year THEN deer_share END), 1) AS deer_share,
       ROUND(AVG(all_share), 1)  AS all_share_5yr,
       ROUND(AVG(deer_share), 1) AS deer_share_5yr
  FROM shares
 GROUP BY bin, label
 ORDER BY bin;
