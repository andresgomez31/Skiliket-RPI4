# model.py
from supabase import create_client
from dotenv import load_dotenv
import os
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error
import pickle
import argparse

load_dotenv()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Train models against a Supabase schema")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--simulation", action="store_true", help="use the 'simulation' schema")
    group.add_argument("--public", action="store_true", help="use the 'public' schema (default)")
    parser.add_argument("--schema", type=str, help="explicit schema name (overrides flags)")
    return parser.parse_args(argv)


def get_supabase_client(schema_name=None):
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise SystemExit("Set SUPABASE_URL and SUPABASE_KEY environment variables.")
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    # If client has a .schema method that returns a scoped client, use it
    if schema_name and hasattr(client, "schema") and callable(getattr(client, "schema")):
        try:
            client = client.schema(schema_name)
        except Exception:
            # If schema() modifies client in place or behaves differently, ignore errors
            pass
    return client


def fetch_all_rows(client, table="measures", page_size=1000):
    all_rows = []
    start = 0
    while True:
        end = start + page_size - 1
        print("Rows from", start, "to", end)
        resp = (
            client.table(table)
            .select("*")
            .range(start, end)
            .execute()
        )
        batch = resp.data or []
        if not batch:
            break
        all_rows.extend(batch)
        start += page_size
    return all_rows


def clean_dataframe(all_rows):
    print("Cleaning and parsing data...")
    df = pd.DataFrame(all_rows)
    # convert measured_at to integer timestamp (ns)
    if "measured_at" in df.columns:
        df["measured_at"] = pd.to_datetime(df["measured_at"], format="mixed").astype("int64")
    df = df.apply(pd.to_numeric, errors="coerce")
    df = df.dropna().reset_index(drop=True)
    print("Finished data cleanup")
    return df


def train_and_save_models(df, models_dir="models", sample_frac=None):
    # optionally sample to reduce size
    if sample_frac:
        n_sample = max(1, int(len(df) * sample_frac))
        df_sample = df.sample(n=n_sample, random_state=40).reset_index(drop=True)
        print(f"Using {len(df_sample)} rows (~{sample_frac*100:.0f}% of {len(df)}) for training")
    else:
        df_sample = df

    models = df.columns[1:]  # assume first column is target index or time

    os.makedirs(models_dir, exist_ok=True)

    for model_name in models:
        print("\n-----------------------------------")
        print(f"Training model for {model_name}...")
        X = df_sample.drop(columns=[model_name])
        Y = df_sample[model_name]

        X_train, X_test, Y_train, Y_test = train_test_split(
            X, Y, test_size=0.2, shuffle=True, random_state=40
        )

        print("Started regression model")
        model = RandomForestRegressor(n_estimators=2000)
        model.fit(X_train, Y_train)
        print("Finished regression model")

        preds = model.predict(X_test)
        mse = mean_squared_error(Y_test, preds)
        print("MSE:", mse)

        out_path = os.path.join(models_dir, f"{model_name}.pkl")
        with open(out_path, "wb") as f:
            pickle.dump(model, f)
        print(f"Model saved as {out_path}")
        print("-----------------------------------\n")

