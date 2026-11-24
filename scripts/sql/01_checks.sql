-- Data checks: run before anything is published.
-- Every row must come back with passed = 1, or the build stops.
WITH
state_2025 AS (SELECT value_2025 AS v FROM statewide WHERE measure = 'total_crashes'),
state_2024 AS (SELECT value_2024 AS v FROM statewide WHERE measure = 'total_crashes'),
deer_2025  AS (SELECT value_2025 AS v FROM statewide WHERE measure = 'deer_crashes'),
deer_2024  AS (SELECT value_2024 AS v FROM statewide WHERE measure = 'deer_crashes')
SELECT 'County crashes add up to the statewide total (2025)' AS check_name,
       (SELECT v FROM state_2025) AS expected,
       (SELECT SUM(total) FROM county_crashes WHERE year = 2025) AS actual
UNION ALL
SELECT 'County crashes add up to the statewide total (2024)',
       (SELECT v FROM state_2024),
       (SELECT SUM(total) FROM county_crashes WHERE year = 2024)
UNION ALL
SELECT 'Each county''s severity counts add up to its total',
       0,
       (SELECT COUNT(*) FROM county_crashes WHERE fatal + injury + pdo <> total)
UNION ALL
SELECT 'Each county''s road types add up to its total (2025)',
       0,
       (SELECT COUNT(*) FROM county_crashes
         WHERE year = 2025
           AND interstate + us_route + state_route + local_street + route_unknown <> total)
UNION ALL
SELECT 'County deer crashes add up to the statewide total (2025)',
       (SELECT v FROM deer_2025),
       (SELECT SUM(deer_crashes) FROM deer_crashes WHERE year = 2025)
UNION ALL
SELECT 'County deer crashes add up to the statewide total (2024)',
       (SELECT v FROM deer_2024),
       (SELECT SUM(deer_crashes) FROM deer_crashes WHERE year = 2024)
UNION ALL
SELECT 'No county has more deer crashes than crashes',
       0,
       (SELECT COUNT(*) FROM deer_crashes d
          JOIN county_crashes c ON c.county = d.county AND c.year = d.year
         WHERE d.deer_crashes > c.total)
UNION ALL
SELECT 'Every county matches across all four county tables',
       83 * 4,
       (SELECT COUNT(*) FROM county_crashes WHERE year = 2025 AND county IN (SELECT county FROM population))
     + (SELECT COUNT(*) FROM county_crashes WHERE year = 2024 AND county IN (SELECT county FROM population))
     + (SELECT COUNT(*) FROM deer_crashes   WHERE year = 2025 AND county IN (SELECT county FROM population))
     + (SELECT COUNT(*) FROM deer_crashes   WHERE year = 2024 AND county IN (SELECT county FROM population))
UNION ALL
SELECT 'Time-of-day, day-of-week and month tables match yearly totals',
       0,
       (SELECT COUNT(*) FROM (
          SELECT y.year FROM statewide_by_year y
            JOIN (SELECT year, SUM(all_crashes) AS n FROM time_of_day GROUP BY year) t USING (year)
            JOIN (SELECT year, SUM(crashes) AS n FROM day_of_week GROUP BY year) w USING (year)
            JOIN (SELECT year, SUM(crashes) AS n FROM month_totals GROUP BY year) m USING (year)
           WHERE t.n <> y.crashes OR w.n <> y.crashes OR m.n <> y.crashes))
UNION ALL
SELECT 'Crash types add up to the 2025 total',
       (SELECT v FROM state_2025),
       (SELECT SUM(crashes) FROM crash_types);
