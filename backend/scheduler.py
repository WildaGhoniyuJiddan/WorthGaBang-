from apscheduler.schedulers.blocking import BlockingScheduler

from app.jobs import run_daily_facebook, run_weekly_queries


def main() -> None:
    scheduler = BlockingScheduler(timezone="Asia/Jakarta")
    scheduler.add_job(run_weekly_queries, "cron", day_of_week="sun", hour=3, id="ecommerce-weekly")
    scheduler.add_job(run_daily_facebook, "interval", days=1, id="facebook-daily")
    print("HargaPas scheduler aktif: weekly e-commerce + daily Facebook cycle")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    main()
