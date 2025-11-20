"""
generate_simulation.py
Generates 1 year of simulated IoT measures for 3 campus nodes and inserts into Supabase.
"""

from supabase import create_client
from dotenv import load_dotenv
import os
import math
import random
from datetime import datetime, timedelta, time, date
from typing import Tuple, List, Dict

# ---------- CONFIG ----------
START_DATE = datetime(2024, 1, 1)
YEAR_LENGTH_DAYS = 365
STEP_MINUTES = 5
BATCH_SIZE = 1000
# ----------------------------

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise SystemExit("Set SUPABASE_URL and SUPABASE_KEY environment variables.")

client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------- NODES ----------
NODES = [
    {"name": "Gym", "location": ( -100.0, 20.0 )},
    {"name": "Food center", "location": ( -100.001, 20.001 )},
    {"name": "Library", "location": ( -100.002, 20.002 )},
]

# ---------- Helpers ----------
def nth_monday_of_month(year: int, month: int, n: int) -> date:
    d = date(year, month, 1)
    days_to_mon = (0 - d.weekday()) % 7
    first_monday = d + timedelta(days=days_to_mon)
    return first_monday + timedelta(weeks=(n - 1))

def semester_ranges_for_year(year:int) -> List[Tuple[datetime, datetime]]:
    s1_start = datetime.combine(nth_monday_of_month(year, 2, 2), time(0,0))
    s1_end = datetime.combine(nth_monday_of_month(year, 6, 2), time(23,59,59))
    s2_start = datetime.combine(nth_monday_of_month(year, 8, 2), time(0,0))
    s2_end = datetime.combine(nth_monday_of_month(year, 12, 1), time(23,59,59))
    return [(s1_start, s1_end), (s2_start, s2_end)]

TEC_PATTERN = [1,2,3,4,5,6, 1,2,3,4,5,6, 1,2,3,4,5]
PATTERN_LEN = len(TEC_PATTERN)

def week_phase_for_dt(dt: datetime, semester_ranges):
    for (start, end) in semester_ranges:
        if start <= dt <= end:
            days = (dt.date() - start.date()).days
            return TEC_PATTERN[(days // 7) % PATTERN_LEN]
    return 0

# ---------- Occupancy ----------
def occupancy_multiplier(dt: datetime, location_name: str, semester_ranges) -> float:
    weekday = dt.weekday()
    hour = dt.hour + dt.minute / 60

    if weekday == 6: dow = 0.05
    elif weekday == 5: dow = 0.3
    else: dow = 1.0

    if 7 <= hour < 9: hour_pref = 0.9
    elif 9 <= hour < 12: hour_pref = 1.0
    elif 12 <= hour < 14: hour_pref = 1.2
    elif 14 <= hour < 17: hour_pref = 0.9
    elif 17 <= hour < 21: hour_pref = 1.1
    else: hour_pref = 0.2

    phase = week_phase_for_dt(dt, semester_ranges)

    if phase == 0:
        phase_factor = 0.6
    elif phase in (1,2,3):
        phase_factor = 1.0
    elif phase == 4:
        phase_factor = 0.9
    elif phase == 5:
        phase_factor = 0.6
    elif phase == 6:
        phase_factor = 0.5
    else:
        phase_factor = 1.0

    if location_name == "Gym":
        base = 0.7
        loc_pref = base * (1.2 if phase in (1,2,3) else 0.7 if phase==5 else 1.0)
        if 17 <= hour < 21: loc_pref *= 1.3
    elif location_name == "Food center":
        base = 0.9
        loc_pref = base * (1.15 if phase in (1,2,3) else 0.8 if phase==5 else 1.0)
        if 12 <= hour < 14: loc_pref *= 1.8
    elif location_name == "Library":
        base = 0.5
        loc_pref = base * (1.4 if phase==5 else 1.2 if phase==4 else 0.9)
        if 18 <= hour < 23: loc_pref *= 1.4
    else:
        loc_pref = 1.0

    occ = dow * hour_pref * phase_factor * loc_pref
    return max(0.0, min(1.5, occ + random.gauss(0, 0.05)))

# ---------- Sensors ----------
def uv_from_time(dt: datetime, cloud_factor: float=1.0) -> float:
    hour = dt.hour + dt.minute/60
    angle = (hour - 13)/12 * math.pi
    uv_base = max(0.0, math.cos(angle))
    return uv_base * 8.0 * cloud_factor

def co2_from_occ(occ: float, location_name: str) -> float:
    base = 420
    vent = {"Food center":0.8, "Gym":0.9, "Library":0.7}.get(location_name, 0.85)
    rise = occ * (500/vent)
    return base + rise + random.gauss(0,10)

def humidity_from_occ(dt, occ, location_name):
    month = dt.month
    if month in (12,1,2): seasonal = 35
    elif month in (3,4,5): seasonal = 45
    elif month in (6,7,8): seasonal = 50
    else: seasonal = 55
    val = seasonal + occ*8 + random.gauss(0,2)
    return max(10, min(90, val))

def noise_from_occ(occ, location_name):
    base = {"Library":35,"Gym":50,"Food center":60}.get(location_name,45)
    val = base + occ*25 + random.gauss(0,3)
    return max(20, min(120, val))

# ---------- Supabase helper ----------
def _resp_data(resp, allow_empty_select=True, expect_inserted=False):
    if isinstance(resp, dict): data = resp.get("data")
    else: data = getattr(resp, "data", None)

    if data is None:
        raise RuntimeError(f"Supabase request failed: {resp}")

    if expect_inserted and isinstance(data, list) and not data:
        raise RuntimeError(f"Insert returned empty: {resp}")

    return data

# ---------- Ensure nodes ----------
def ensure_nodes_and_locations():
    qry = client.schema("simulation").table("nodes").select("id,name").execute()
    rows = _resp_data(qry)

    existing = {r["name"]: r["id"] for r in rows or []}
    node_records = []
    node_id_map = {}

    for n in NODES:
        if n["name"] in existing:
            node_id_map[n["name"]] = existing[n["name"]]
        else:
            node_records.append({"name": n["name"]})

    if node_records:
        ins = client.schema("simulation").table("nodes").insert(node_records).execute()
        inserted = _resp_data(ins, expect_inserted=True)
        for r in inserted:
            node_id_map[r["name"]] = r["id"]

    qry2 = client.schema("simulation").table("locations").select("node").execute()
    loc_rows = _resp_data(qry2)
    existing_loc = {r["node"] for r in loc_rows or []}

    loc_records = []
    for n in NODES:
        nid = node_id_map[n["name"]]
        if nid not in existing_loc:
            point = f"({n['location'][0]},{n['location'][1]})"
            loc_records.append({
                "node": nid,
                "location": point,
                "from_dt": START_DATE.isoformat(),
                "to_dt": (START_DATE + timedelta(days=365*5)).isoformat()
            })

    if loc_records:
        ins2 = client.schema("simulation").table("locations").insert(loc_records).execute()
        _resp_data(ins2, expect_inserted=True)

    return node_id_map

# ---------- Main generation ----------
def generate_and_insert():
    node_id_map = ensure_nodes_and_locations()

    semester_ranges = semester_ranges_for_year(START_DATE.year)
    semester_ranges += semester_ranges_for_year(START_DATE.year - 1)
    semester_ranges += semester_ranges_for_year(START_DATE.year + 1)

    dt = START_DATE
    end_dt = START_DATE + timedelta(days=YEAR_LENGTH_DAYS)
    step = timedelta(minutes=STEP_MINUTES)

    batch = []
    total = 0

    print("Starting generation...")

    while dt < end_dt:
        for n in NODES:
            nid = node_id_map[n["name"]]
            occ = occupancy_multiplier(dt, n["name"], semester_ranges)

            spike = (random.random() < 0.001)

            humidity = humidity_from_occ(dt, occ, n["name"])
            co2 = co2_from_occ(occ*(3 if spike else 1), n["name"])
            noise = noise_from_occ(occ*(3 if spike else 1), n["name"])

            cloud = 0.9 if random.random() < 0.05 else 1.0
            uv_raw = uv_from_time(dt, cloud)

            indoor = {"Gym":0.25,"Food center":0.4,"Library":0.15}.get(n["name"],0.3)
            uv = max(0.0, uv_raw * indoor * (0.5+0.5*occ) + random.gauss(0,0.05))

            rec = {
                "node": nid,
                "humidity": round(float(humidity),2),
                "co2": round(float(co2),1),
                "noise": round(float(noise),2),
                "uv": round(float(uv),3),
                "measured_at": dt.isoformat()
            }

            batch.append(rec)

        if len(batch) >= BATCH_SIZE:
            resp = client.schema("simulation").table("measures").insert(batch).execute()
            _resp_data(resp)
            total += len(batch)
            print(f"Inserted {total}...")
            batch = []

        dt += step

    if batch:
        resp = client.schema("simulation").table("measures").insert(batch).execute()
        _resp_data(resp)
        total += len(batch)
        print("Final inserted:", total)

if __name__ == "__main__":
    generate_and_insert()

