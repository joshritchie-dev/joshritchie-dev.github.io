-- Warnings, not failures: counties whose crash count moved more than 40%
-- in a year. Big swings in small counties are often reporting changes,
-- so the page flags them instead of treating them as real trends.
SELECT cur.county,
       prev.total AS total_prev,
       cur.total,
       ROUND(100.0 * (cur.total - prev.total) / prev.total, 1) AS change_pct
  FROM county_crashes cur
  JOIN county_crashes prev ON prev.county = cur.county AND prev.year = cur.year - 1
 WHERE cur.year = :year
   AND ABS(cur.total - prev.total) > 0.4 * prev.total
 ORDER BY ABS(cur.total - prev.total) * 1.0 / prev.total DESC;
