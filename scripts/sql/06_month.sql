-- Crashes by month: the latest year against the range of the four years before it.
SELECT month,
       MAX(CASE WHEN year = :year THEN crashes END) AS crashes,
       MIN(CASE WHEN year < :year THEN crashes END) AS prior_min,
       MAX(CASE WHEN year < :year THEN crashes END) AS prior_max,
       ROUND(AVG(CASE WHEN year < :year THEN crashes END), 0) AS prior_avg
  FROM month_totals
 WHERE year BETWEEN :year - 4 AND :year
 GROUP BY month
 ORDER BY month;
