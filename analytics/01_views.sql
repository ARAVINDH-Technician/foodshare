-- FoodShare India: SQL analytics layer (MySQL 8+). Run in MySQL Workbench AFTER: migrate + seed_demo
-- Django stores times in UTC, so views add 330 minutes (IST) where hours/days matter.
USE foodshare;

-- 1. Base view: one row per donation with computed state, IST time parts and delays
CREATE OR REPLACE VIEW v_donations AS
SELECT d.id,
       COALESCE(NULLIF(u.organisation,''), u.username) AS donor_name,
       d.donor_type,
       COALESCE(NULLIF(n.organisation,''), n.username) AS ngo_name,
       d.area, d.food, d.portions, d.status,
       CASE WHEN d.status IN ('available','pending') AND d.deadline <= UTC_TIMESTAMP()
            THEN 'expired' ELSE d.status END AS state,
       DATE_ADD(d.created, INTERVAL 330 MINUTE) AS created_ist,
       DATE(DATE_ADD(d.created, INTERVAL 330 MINUTE)) AS created_date,
       HOUR(DATE_ADD(d.created, INTERVAL 330 MINUTE)) AS created_hour,
       DAYNAME(DATE_ADD(d.created, INTERVAL 330 MINUTE)) AS weekday,
       WEEKDAY(DATE_ADD(d.created, INTERVAL 330 MINUTE)) AS weekday_no,
       DATE_SUB(DATE(DATE_ADD(d.created, INTERVAL 330 MINUTE)),
                INTERVAL WEEKDAY(DATE_ADD(d.created, INTERVAL 330 MINUTE)) DAY) AS week_start,
       d.requested_at, d.responded_at, d.collected_at,
       TIMESTAMPDIFF(MINUTE, d.requested_at, d.responded_at) AS response_minutes,
       TIMESTAMPDIFF(MINUTE, d.requested_at, d.collected_at) AS collection_minutes
FROM core_donation d
JOIN core_user u ON u.id = d.donor_id
LEFT JOIN core_user n ON n.id = d.ngo_id;

-- 2. Area summary: how much food each area posts, saves and wastes
CREATE OR REPLACE VIEW v_area_summary AS
SELECT area,
       COUNT(*) AS donations,
       SUM(portions) AS portions_posted,
       SUM(CASE WHEN state='collected' THEN portions ELSE 0 END) AS portions_collected,
       SUM(CASE WHEN state='expired'   THEN portions ELSE 0 END) AS portions_wasted,
       ROUND(100*SUM(state='collected')/NULLIF(SUM(state IN ('collected','expired')),0),1) AS collection_rate_pct
FROM v_donations GROUP BY area;

-- 3. Surplus vs demand by area (open food vs active NGO needs)
CREATE OR REPLACE VIEW v_surplus_vs_demand AS
SELECT a.area,
       COALESCE(s.surplus,0) AS surplus_portions,
       COALESCE(n.needed,0)  AS meals_needed,
       COALESCE(s.surplus,0) - COALESCE(n.needed,0) AS gap,
       CASE WHEN COALESCE(s.surplus,0) - COALESCE(n.needed,0) < 0 THEN 'Demand not met'
            WHEN COALESCE(s.surplus,0) - COALESCE(n.needed,0) > 0 THEN 'Surplus to redistribute'
            ELSE 'Balanced' END AS status_label
FROM (SELECT area FROM core_donation UNION SELECT area FROM core_foodneed) a
LEFT JOIN (SELECT area, SUM(portions) AS surplus FROM core_donation
           WHERE status='available' AND deadline > UTC_TIMESTAMP() GROUP BY area) s ON s.area = a.area
LEFT JOIN (SELECT area, SUM(meals) AS needed FROM core_foodneed WHERE active=1 GROUP BY area) n ON n.area = a.area;

-- 4. Redistribution plan: move food from surplus areas to areas with unmet demand
CREATE OR REPLACE VIEW v_redistribution AS
SELECT s.area AS from_area, d.area AS to_area, LEAST(s.gap, -d.gap) AS portions_to_move
FROM v_surplus_vs_demand s JOIN v_surplus_vs_demand d ON s.gap > 0 AND d.gap < 0
ORDER BY portions_to_move DESC;

-- 5. Peak posting hours by donor type
CREATE OR REPLACE VIEW v_peak_hours AS
SELECT donor_type, created_hour, COUNT(*) AS donations, SUM(portions) AS portions_posted
FROM v_donations GROUP BY donor_type, created_hour;

-- 6. Day-of-week pattern
CREATE OR REPLACE VIEW v_weekday_pattern AS
SELECT weekday, weekday_no, COUNT(*) AS donations, SUM(portions) AS portions_posted,
       SUM(CASE WHEN state='expired' THEN portions ELSE 0 END) AS portions_wasted
FROM v_donations GROUP BY weekday, weekday_no;

-- 7. Donor reliability with ranking (window function RANK)
CREATE OR REPLACE VIEW v_donor_reliability AS
SELECT t.*, RANK() OVER (ORDER BY t.collection_rate_pct DESC) AS rank_no
FROM (SELECT donor_name, donor_type, COUNT(*) AS donations, SUM(portions) AS portions_posted,
             SUM(state='collected') AS collected, SUM(state='expired') AS expired,
             ROUND(100*SUM(state='collected')/NULLIF(SUM(state IN ('collected','expired')),0),1) AS collection_rate_pct
      FROM v_donations GROUP BY donor_name, donor_type) t;

-- 8. NGO performance: claims, collections and speed
CREATE OR REPLACE VIEW v_ngo_performance AS
SELECT ngo_name, COUNT(*) AS claims, SUM(state='collected') AS collected,
       SUM(CASE WHEN state='collected' THEN portions ELSE 0 END) AS portions_collected,
       ROUND(AVG(collection_minutes),0) AS avg_collection_minutes
FROM v_donations WHERE ngo_name IS NOT NULL GROUP BY ngo_name;

-- 9. How fast donors respond to NGO requests
CREATE OR REPLACE VIEW v_donor_response AS
SELECT donor_name, COUNT(response_minutes) AS responses, ROUND(AVG(response_minutes),0) AS avg_response_minutes
FROM v_donations WHERE response_minutes IS NOT NULL GROUP BY donor_name;

-- 10. Weekly trend with week-on-week change and 4-week moving average (window functions LAG, AVG OVER)
CREATE OR REPLACE VIEW v_weekly_trend AS
SELECT w.*,
       LAG(w.portions_posted) OVER (ORDER BY w.week_start) AS prev_week,
       ROUND(100*(w.portions_posted - LAG(w.portions_posted) OVER (ORDER BY w.week_start))
             / NULLIF(LAG(w.portions_posted) OVER (ORDER BY w.week_start),0),1) AS wow_change_pct,
       ROUND(AVG(w.portions_posted) OVER (ORDER BY w.week_start ROWS BETWEEN 3 PRECEDING AND CURRENT ROW),1) AS moving_avg_4w
FROM (SELECT week_start, COUNT(*) AS donations, SUM(portions) AS portions_posted,
             SUM(CASE WHEN state='collected' THEN portions ELSE 0 END) AS portions_collected,
             SUM(CASE WHEN state='expired' THEN portions ELSE 0 END) AS portions_wasted
      FROM v_donations GROUP BY week_start) w;

-- 11. Waste by donor type
CREATE OR REPLACE VIEW v_waste_by_type AS
SELECT donor_type, SUM(portions) AS portions_posted,
       SUM(CASE WHEN state='expired' THEN portions ELSE 0 END) AS portions_wasted,
       ROUND(100*SUM(CASE WHEN state='expired' THEN portions ELSE 0 END)/SUM(portions),1) AS waste_pct
FROM v_donations GROUP BY donor_type;

-- Try them (take screenshots for your report):
-- SELECT * FROM v_area_summary ORDER BY portions_wasted DESC;
-- SELECT * FROM v_surplus_vs_demand ORDER BY gap;
-- SELECT * FROM v_redistribution;
-- SELECT * FROM v_donor_reliability ORDER BY rank_no;
-- SELECT * FROM v_weekly_trend ORDER BY week_start;
