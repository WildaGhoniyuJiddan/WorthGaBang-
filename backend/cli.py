import argparse

from app.jobs import run_all_queries, run_cycle


def main() -> None:
    parser = argparse.ArgumentParser(description="HargaPas background jobs")
    parser.add_argument("command", choices=("scrape", "scrape-all", "import-processed"))
    parser.add_argument("--query", default=None)
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()
    if args.command == "import-processed":
        from scripts.import_processed_hardware import import_dataset, resolve_data_dir

        print(import_dataset(resolve_data_dir(args.data_dir)))
        return
    result = run_cycle(args.query) if args.command == "scrape" else run_all_queries()
    print(result)


if __name__ == "__main__":
    main()
