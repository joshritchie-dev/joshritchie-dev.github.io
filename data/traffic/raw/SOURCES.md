# Michigan traffic data sources

Every file in this folder is a table copied from a public report. Nothing here is estimated. The build script (`scripts/build_traffic.py`) loads these files into a SQLite database and checks that the totals add up before it writes `data/traffic.json`.

| File | What it holds | Source |
|---|---|---|
| county_crashes_2025.csv | 2025 crashes by county, by severity and road class | Michigan State Police, *2025 County Crash Report* (Traffic Crash Reporting Unit) |
| county_crashes_2024.csv | 2024 crashes by county, by severity and road class | Michigan Traffic Crash Facts, *2024 Traffic Crash Summary* (County/Community volume) |
| deer_county_2025.csv | 2025 deer-involved crashes by county and road class | Michigan Traffic Crash Facts, *2025 Deer Involved Crash Summary by County* |
| deer_county_2024.csv | 2024 deer-involved crashes by county | Michigan Traffic Crash Facts, *2024 Deer* (Statewide volume) |
| population_2024.csv | July 1, 2024 county population estimates | U.S. Census Bureau, via Michigan Senate Fiscal Agency, *Michigan Population by County* |
| statewide_by_year.csv | Statewide crashes 2004-2025; miles driven, registrations and population 2016-2025 | MSP *Crash Decade at a Glance* (2025 edition); 2025 miles driven from MTCF *At-a-Glance* |
| time_of_day.csv | Crashes and deer crashes by time of day, 2021-2025 | MTCF *2025 Statewide County Summary* |
| day_of_week.csv | Crashes by day of week, 2021-2025 | MTCF *2025 Statewide County Summary* |
| month.csv | Crashes by month, 2021-2025 | MTCF *2025 Statewide County Summary* |
| crash_type_2025.csv | 2025 crashes by crash type | MTCF *2025 Statewide County Summary* |
| statewide_2025.csv | Selected statewide counts, 2024 and 2025 | MSP *2024-2025 Year End Comparison*; MTCF *At-a-Glance* |

To add a new year: copy the new year's tables into files with the same columns, update the year in `scripts/build_traffic.py`, and run the script. It stops with an error if any total doesn't add up.

Fatal-crash counts appear in the county files only so the severity check can confirm each row adds up. The dashboard does not show them.
