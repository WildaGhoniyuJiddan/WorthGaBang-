import argparse

from app.jobs import run_all_queries, run_cycle


def main() -> None:
    parser = argparse.ArgumentParser(description="HargaPas background jobs")
    parser.add_argument("command", choices=("scrape", "scrape-all"))
    parser.add_argument("--query", default=None)
    args = parser.parse_args()
    result = run_cycle(args.query) if args.command == "scrape" else run_all_queries()
    print(result)


if __name__ == "__main__":
    main()

