import os
import pickle
import argparse
import numpy as np
import pandas as pd
from sklearn.metrics import mean_squared_error
import warnings
warnings.filterwarnings("ignore", message="X does not have valid feature names")


import skiliket.func as sk

MODELS_DIR = "models"


def load_model(path):
    with open(path, "rb") as f:
        return pickle.load(f)


def test_model(model, df, target_column):
    X = df.drop(columns=[target_column])
    y_true = df[target_column]

    preds = model.predict(X)

    mse = mean_squared_error(y_true, preds)
    mae = np.mean(np.abs(y_true - preds))

    return mse, mae


def main(argv=None):
    # --- parse args (same logic as training) ---
    args = sk.parse_args(argv)
    schema = args.schema or ("simulation" if args.simulation else "public")

    print(f"Using schema: {schema}")

    # --- connect ---
    client = sk.get_supabase_client(schema)

    # --- fetch rows ---
    print("Fetching data...")
    rows = sk.fetch_all_rows(client, table="measures")

    if not rows:
        print("No rows found in table 'measures'. Exiting.")
        return

    # --- clean ---
    df = sk.clean_dataframe(rows)
    print("Final dataframe shape:", df.shape)

    # --- test each model ---
    print("\n=== Testing stored models ===")
    for fname in os.listdir(f"{schema}_{MODELS_DIR}"):
        if not fname.endswith(".pkl") or fname.startswith(".") or fname.startswith("measured_at"):
            continue

        target_name = fname[:-4]  # remove .pkl
        model_path = os.path.join(f"{schema}_{MODELS_DIR}", fname)

        if target_name not in df.columns:
            print(f"[SKIP] Model {fname}: column '{target_name}' not in dataframe")
            continue

        print(f"\n--- Model: {target_name} ---")
        model = load_model(model_path)

        mse, mae = test_model(model, df, target_name)

        print(f"MSE: {mse:.6f}")
        print(f"MAE: {mae:.6f}")

        # --- Demonstration of predictions on sample inputs ---
        print("\nSample predictions:")

        # Pick 5 evenly spaced rows to show variety
        sample_indices = np.linspace(0, len(df) - 1, 5, dtype=int)

        # Collect table rows
        table_rows = []

        for idx in sample_indices:
            row = df.iloc[idx]

            X_input = row.drop(labels=[target_name])
            real_value = row[target_name]
            pred_value = model.predict([X_input.to_numpy()])[0]  # ensure no feature-name warning

            table_rows.append({
                "index": idx,
                "pred": pred_value,
                "real": real_value,
            })

        # Pretty print table
        print("\n" + "-" * 46)
        print(f"{'Row':<6} | {'Predicted':<15} | {'Real':<15}")
        print("-" * 46)

        for r in table_rows:
            print(f"{r['index']:<6} | {r['pred']:<15.4f} | {r['real']:<15.4f}")

        print("-" * 46)


    print("\nDone.")


if __name__ == "__main__":
    main()
