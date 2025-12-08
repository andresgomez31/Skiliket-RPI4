"""
generate_simulation.py
Generates 1 year of simulated IoT measures (with temperature) 
for the campus nodes stored in the database.
"""

from supabase import create_client
from dotenv import load_dotenv
import os
import math
import random
from datetime import datetime, timedelta, time, date, timezone
from typing import Tuple, List, Dict

# ---------- CONFIG ----------
START_DATE = datetime(2025, 11, 15)
YEAR_LENGTH_DAYS = 18
STEP_MINUTES = 5
BATCH_SIZE = 1000
SCHEMA = "public"


load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise SystemExit("Set SUPABASE_URL and SUPABASE_KEY environment variables.")

client = create_client(SUPABASE_URL, SUPABASE_KEY)

# UPDATED NODES: join with locations and parse coordinates
# Fetch nodes and locations separately and join in Python (filter locations with to_dt > now)
nodes_raw = client.schema(SCHEMA).from_("nodes").select("*").execute().data or []
print ("Fetched nodes:", len(nodes_raw))
locations_raw = client.schema(SCHEMA).from_("locations").select("*").execute().data or []
print ("Fetched locations:", len(locations_raw))

def parse_point(pt: str):
    pt = pt.strip("()")
    lat, lon = pt.split(",")
    return float(lat), float(lon)

def parse_dt(dt_str: str) -> datetime:
    if not dt_str:
        return datetime.min.replace(tzinfo=timezone.utc)
    # preserve whether the string had a trailing Z (UTC) so we can attach tzinfo when needed
    s = dt_str
    has_z = s.endswith("Z")
    if has_z:
        s = s.rstrip("Z")
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        # fallback common formats
        try:
            dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    else:
        return dt.astimezone(timezone.utc)

now = datetime.now(timezone.utc)

# keep only locations with to_dt > now
current_locations = [l for l in locations_raw if (parse_dt(l.get("to_dt")) > now or l.get("to_dt") is None)]

print ("Using current locations:", len(current_locations))

# join nodes with their current location (if any)
NODES = []
for n in nodes_raw:
    loc = next((l for l in current_locations if l.get("node") == n.get("id")), None)
    if not loc:
        continue
    lat, lon = parse_point(loc.get("location", "(0,0)"))
    NODES.append({
        "id": n.get("id"),
        "name": n.get("name", "Unknown"),
        "lat": lat,
        "lon": lon,
    })

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

# ---------- Temperature ----------
def temperature_from_season_and_time(dt: datetime, location_name: str, occ: float) -> float:
    # Seasonal baseline
    month = dt.month
    if month in (12,1,2): base = 17  # Winter
    elif month in (3,4,5): base = 22  # Spring
    elif month in (6,7,8): base = 26  # Summer
    else: base = 21                   # Autumn

    # Daily curve using sine wave
    hour = dt.hour + dt.minute / 60
    daily_variation = 6 * math.sin((hour - 14) / 24 * 2 * math.pi)

    # Indoor adjustment per location
    indoor_factor = {"Gym": 1.5, "Food center": 1.0, "Library": 0.5}.get(location_name, 1.0)

    # Occupancy warms rooms slightly
    occ_heat = occ * 1.8

    temp = base + daily_variation + occ_heat + indoor_factor
    temp += random.gauss(0, 0.6)

    return max(10, min(40, temp))

# ---------- Other sensors ----------
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

# ---------- Main generation ----------
def generate_and_insert():
    print("Using existing nodes from DB:", len(NODES))

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
            occ = occupancy_multiplier(dt, n["name"], semester_ranges)

            spike = (random.random() < 0.001)

            temp = temperature_from_season_and_time(dt, n["name"], occ)
            humidity = humidity_from_occ(dt, occ, n["name"])
            co2 = co2_from_occ(occ*(3 if spike else 1), n["name"])
            noise = noise_from_occ(occ*(3 if spike else 1), n["name"])

            cloud = 0.9 if random.random() < 0.05 else 1.0
            uv_raw = uv_from_time(dt, cloud)

            indoor = {"Gym":0.25,"Food center":0.4,"Library":0.15}.get(n["name"],0.3)
            uv = max(0.0, uv_raw * indoor * (0.5+0.5*occ) + random.gauss(0,0.05))

            rec = {
                "node": n["id"],
                "temperature": round(float(temp), 2),
                "humidity": round(float(humidity), 2),
                "co2": round(float(co2), 1),
                "noise": round(float(noise), 2),
                "uv": round(float(uv), 3),
                "measured_at": dt.isoformat()
            }

            batch.append(rec)

        if len(batch) >= BATCH_SIZE:
            resp = client.schema(SCHEMA).table("measures").insert(batch).execute()
            if resp.data is None:
                raise RuntimeError("Insert failed")
            total += len(batch)
            print(f"Inserted {total}...")
            batch = []

        dt += step

    if batch:
        resp = client.schema(SCHEMA).table("measures").insert(batch).execute()
        if resp.data is None:
            raise RuntimeError("Final insert failed")
        total += len(batch)
        print("Final inserted:", total)

if __name__ == "__main__":
    generate_and_insert()
