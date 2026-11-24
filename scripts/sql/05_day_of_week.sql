-- Average crashes per day for each weekday. Some weekdays occur 53 times
-- in a year, so a recursive calendar counts how many of each there were.
WITH RECURSIVE calendar(d) AS (
  SELECT date(:year || '-01-01')
  UNION ALL
  SELECT date(d, '+1 day') FROM calendar WHERE d < date(:year || '-12-31')
),
weekday_counts AS (
  -- SQLite's %w: 0 = Sunday ... 6 = Saturday. Convert to 1 = Monday ... 7 = Sunday.
  SELECT CASE strftime('%w', d) WHEN '0' THEN 7 ELSE CAST(strftime('%w', d) AS INTEGER) END AS dow,
         COUNT(*) AS days
    FROM calendar
   GROUP BY dow
)
SELECT w.dow, w.day, w.crashes, k.days,
       ROUND(1.0 * w.crashes / k.days, 0) AS per_day,
       ROUND(100.0 * w.crashes / SUM(w.crashes) OVER (), 1) AS share
  FROM day_of_week w
  JOIN weekday_counts k USING (dow)
 WHERE w.year = :year
 ORDER BY w.dow;
