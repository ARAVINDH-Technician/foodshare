# Power BI dashboard for FoodShare India

## Run order (about 15 minutes)
1. MySQL: `CREATE DATABASE foodshare CHARACTER SET utf8mb4;` then point Django `DATABASES` at it, run `migrate` and `seed_demo`.
2. MySQL Workbench: open `01_views.sql`, run all (lightning icon). You get 11 views, all starting with `v_`.
3. Forecast: `pip install pandas matplotlib sqlalchemy pymysql`, set `DB_NAME`, `DB_USER`, `DB_PASSWORD` in PowerShell
   (`$env:DB_NAME="foodshare"`), then `python analytics/forecast.py`. Results: `analytics_output/`.
4. Power BI Desktop: Get data > MySQL database > Server `127.0.0.1`, Database `foodshare`. Install MySQL Connector/NET if asked.
   Tick the `v_` views. Then Get data > Text/CSV > `analytics_output/powerbi_forecast.csv` and `model_accuracy.csv`.
   (No MySQL? Load `donations.csv` and `needs.csv` from `analytics_output` instead. `donations.csv` has the same columns as `v_donations`.)

## DAX measures (Modeling > New measure, on v_donations)
```
Total Portions     = SUM(v_donations[portions])
Collected Portions = CALCULATE(SUM(v_donations[portions]), v_donations[state] = "collected")
Wasted Portions    = CALCULATE(SUM(v_donations[portions]), v_donations[state] = "expired")
Collection Rate    = DIVIDE([Collected Portions], [Collected Portions] + [Wasted Portions])
Waste %            = DIVIDE([Wasted Portions], [Total Portions])
Donations          = COUNTROWS(v_donations)
```

## Pages
1. **Overview** - cards: Donations, Total Portions, Collected Portions, Wasted Portions, Collection Rate. Line chart: `v_weekly_trend` week_start vs portions_posted + moving_avg_4w. Slicers: area, donor_type.
2. **Areas** - clustered bar: `v_surplus_vs_demand` area vs surplus_portions and meals_needed. Table with gap and status_label (red when gap < 0). Stacked bar: `v_area_summary` collected vs wasted. Table: `v_redistribution`.
3. **Timing** - matrix: `v_peak_hours` donor_type (rows) x created_hour (columns), values donations, heat-map colours. Column chart: `v_weekday_pattern` by weekday (sort by weekday_no).
4. **Partners** - tables: `v_donor_reliability` (sort rank_no), `v_ngo_performance`, `v_donor_response`. Bar: `v_waste_by_type` waste_pct.
5. **Forecast** - line chart from `powerbi_forecast.csv`: x week_start, y portions, legend kind, slicer area (start with "All areas"). Table: `model_accuracy.csv` (MAE per model, selected = TRUE).

## Viva answers
- Why SQL views? One clean layer: Power BI, Pandas and reports all use the same definitions (for example "expired").
- Which window functions? RANK (donor ranking), LAG (week-on-week change), AVG OVER (4-week moving average).
- How is the forecast chosen? Three simple models (naive, 4-week moving average, linear trend) are backtested on the last 4 weeks; the lowest MAE wins per area.
- Limits? About 13 weeks of sample data; real data from partner NGOs would improve it.
