import sys
import skiliket.func as sk

def main(argv=None):
    args = sk.parse_args(argv)

    chosen_schema = ""

    if args.schema:
        chosen_schema = args.schema
    elif args.simulation:
        chosen_schema = "simulation"
    else:
        chosen_schema = "public"

    print(f"Using Supabase schema: {chosen_schema}")

    client = sk.get_supabase_client(schema_name=chosen_schema)
    all_rows = sk.fetch_all_rows(client)

    if not all_rows:
        print("No rows fetched. Exiting.")
        return 1

    df = sk.clean_dataframe(all_rows)

    if df.empty:
        print("DataFrame is empty after cleaning. Exiting.")
        return 1

    sk.train_and_save_models(df, models_dir=f"{chosen_schema}_models", sample_frac=(len(df) > 10000) and 0.1 or None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
