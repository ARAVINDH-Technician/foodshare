"""FoodShare India - weekly surplus forecast + CSV exports for Power BI.
Install:  pip install pandas matplotlib            (MySQL also needs: pip install sqlalchemy pymysql)
Run from the folder that contains manage.py:   python analytics/forecast.py
MySQL:  set DB_NAME=foodshare, DB_USER, DB_PASSWORD, DB_HOST first. Without DB_NAME it reads db.sqlite3.
Output goes to the analytics_output folder.
"""
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote_plus

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "analytics_output"
OUT.mkdir(exist_ok=True)
HORIZON = 4  # weeks to forecast
IST = pd.Timedelta(hours=5, minutes=30)


def connect():
    if os.environ.get("DB_NAME"):
        from sqlalchemy import create_engine
        url = "mysql+pymysql://{}:{}@{}/{}".format(os.environ.get("DB_USER", "root"), quote_plus(os.environ.get("DB_PASSWORD", "")),
                                                   os.environ.get("DB_HOST", "127.0.0.1"), os.environ["DB_NAME"])
        return create_engine(url)
    return sqlite3.connect(ROOT / "db.sqlite3")


def ts(s):
    return pd.to_datetime(s, utc=True, format="mixed").dt.tz_localize(None)


# ---------- load and clean ----------
con = connect()
don = pd.read_sql("""SELECT d.id, COALESCE(NULLIF(u.organisation,''), u.username) AS donor_name, d.donor_type,
       COALESCE(NULLIF(n.organisation,''), n.username) AS ngo_name, d.area, d.portions, d.status,
       d.deadline, d.created, d.requested_at, d.responded_at, d.collected_at
       FROM core_donation d JOIN core_user u ON u.id = d.donor_id LEFT JOIN core_user n ON n.id = d.ngo_id""", con)
need = pd.read_sql("SELECT area, meals, active FROM core_foodneed", con)
if don.empty:
    raise SystemExit("No donations found. Run: python manage.py seed_demo")

for c in ("deadline", "created", "requested_at", "responded_at", "collected_at"):
    don[c] = ts(don[c])
now = pd.Timestamp.now(tz="UTC").tz_localize(None)
don["state"] = np.where(don.status.isin(["available", "pending"]) & (don.deadline <= now), "expired", don.status)
ist = don.created + IST
don["created_ist"], don["created_hour"], don["weekday"] = ist, ist.dt.hour, ist.dt.day_name()
don["week_start"] = ist.dt.normalize() - pd.to_timedelta(ist.dt.weekday, unit="D")
don["response_minutes"] = (don.responded_at - don.requested_at).dt.total_seconds() / 60
don["collection_minutes"] = (don.collected_at - don.requested_at).dt.total_seconds() / 60

keep = ["id", "donor_name", "donor_type", "ngo_name", "area", "portions", "state", "created_ist", "created_hour",
        "weekday", "week_start", "response_minutes", "collection_minutes"]
don[keep].to_csv(OUT / "donations.csv", index=False)
need[need.active == 1][["area", "meals"]].to_csv(OUT / "needs.csv", index=False)

# ---------- weekly surplus per area (portions posted) ----------
wk = don.groupby(["week_start", "area"])["portions"].sum().unstack("area").fillna(0)
wk = wk.reindex(pd.date_range(wk.index.min(), wk.index.max(), freq="7D"), fill_value=0)
this_monday = (now + IST).normalize() - pd.Timedelta(days=(now + IST).weekday())
wk = wk[wk.index < this_monday].iloc[1:]  # complete weeks only: drop current and first partial week
if len(wk) < 4:
    raise SystemExit("Need at least 4 complete weeks of data. Run seed_demo for 90 days of sample data.")
wk["All areas"] = wk.sum(axis=1)


# ---------- three simple models, picked per area by backtest ----------
def naive(y, h): return np.repeat(y[-1], h)
def moving_avg_4w(y, h): return np.repeat(y[-4:].mean(), h)
def linear_trend(y, h):
    b, a = np.polyfit(np.arange(len(y)), y, 1)
    return np.maximum(a + b * np.arange(len(y), len(y) + h), 0)


MODELS = {"naive": naive, "moving_avg_4w": moving_avg_4w, "linear_trend": linear_trend}
fc_rows, acc_rows = [], []
for area in wk.columns:
    y = wk[area].to_numpy(float)
    if len(y) >= 8:  # backtest: predict each of the last 4 weeks one step ahead
        scores = {m: float(np.mean([abs(y[t] - fn(y[:t], 1)[0]) for t in range(len(y) - 4, len(y))])) for m, fn in MODELS.items()}
        best = min(scores, key=scores.get)
    else:
        scores, best = {}, "moving_avg_4w"
    for i, v in enumerate(MODELS[best](y, HORIZON)):
        fc_rows.append({"area": area, "week_start": wk.index[-1] + pd.Timedelta(days=7 * (i + 1)),
                        "portions": round(float(v)), "kind": "Forecast", "model": best})
    for m, s in scores.items():
        acc_rows.append({"area": area, "model": m, "mae_portions": round(s, 1), "selected": m == best})

fc = pd.DataFrame(fc_rows)
actual = wk.rename_axis("week_start").reset_index().melt(id_vars="week_start", var_name="area", value_name="portions")
actual["kind"], actual["model"] = "Actual", ""
pd.concat([actual, fc]).to_csv(OUT / "powerbi_forecast.csv", index=False)
fc.to_csv(OUT / "forecast_next_4_weeks.csv", index=False)
pd.DataFrame(acc_rows).to_csv(OUT / "model_accuracy.csv", index=False)

# ---------- chart ----------
names, cols = list(wk.columns), 2
rows = -(-len(names) // cols)
fig, axes = plt.subplots(rows, cols, figsize=(12, 3 * rows), squeeze=False)
for ax, name in zip(axes.flat, names):
    f = fc[fc.area == name]
    ax.plot(wk.index, wk[name], marker="o", label="Actual")
    ax.plot(f.week_start, f.portions, "--", marker="o", label="Forecast (" + f.model.iloc[0] + ")")
    ax.set_title(name)
    ax.legend(fontsize=7)
    ax.tick_params(axis="x", labelrotation=30, labelsize=7)
for ax in list(axes.flat)[len(names):]:
    ax.axis("off")
fig.tight_layout()
fig.savefig(OUT / "forecast_charts.png", dpi=130)

print("Forecast of portions posted per week (next %d weeks):" % HORIZON)
print(fc.pivot(index="area", columns="week_start", values="portions").to_string())
print("\nModel chosen per area:", fc.groupby("area").model.first().to_dict())
print("Files saved in:", OUT)
