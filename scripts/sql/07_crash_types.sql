-- Crash types ranked, each as a share of all crashes.
SELECT crash_type,
       crashes,
       ROUND(100.0 * crashes / SUM(crashes) OVER (), 1) AS share
  FROM crash_types
 ORDER BY crash_type IN ('Other', 'Unknown'), crashes DESC;
