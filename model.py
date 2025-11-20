from supabase import create_client
from dotenv import load_dotenv
import os
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error
import pickle

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise SystemExit("Set SUPABASE_URL and SUPABASE_KEY environment variables.")

client = create_client (SUPABASE_URL, SUPABASE_KEY)

all_rows = []
page_size = 1000
start = 0

while True:
    end = start + page_size - 1
    print ("Rows from ", start, " to ", end)
    
    resp = (
        client.schema("simulation")
        .table("measures")
        .select("*")
        .range(start, end)
        .execute()
    )
    
    batch = resp.data or []
    if not batch:
        break
    
    all_rows.extend(batch)
    start += page_size

print ("Cleaning and parsing data...")

df = pd.DataFrame(all_rows)
df["measured_at"] = pd.to_datetime(df["measured_at"]).astype("int64")
df = df.apply(pd.to_numeric, errors="coerce")
df = df.dropna()

print ("Finished data cleanup")

X= df.drop(columns=["humidity"])
Y= df["humidity"]

X_train, X_test, Y_train, Y_test = train_test_split(
        X, Y, test_size=0.2, shuffle=True, random_state=40
        )

print ("Started regression model")

model = RandomForestRegressor(n_estimators=2000)
model.fit(X_train, Y_train)

print ("Finished regression model")

preds = model.predict(X_test)
mse = mean_squared_error(Y_test, preds)
print ("MSE: ", mse)

with open("model.pkl", "wb") as f:
    pickle.dump(model, f)

print ("Model saved as model.pkl")

