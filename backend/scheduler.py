from apscheduler.schedulers.blocking import BlockingScheduler

from app.jobs import run_daily_facebook, run_monthly_komponen_retail, run_weekly_queries


def main() -> None:
    scheduler = BlockingScheduler(timezone="Asia/Jakarta")
    scheduler.add_job(run_weekly_queries, "cron", day_of_week="sun", hour=3, id="ecommerce-weekly")
    scheduler.add_job(run_daily_facebook, "interval", days=1, id="facebook-daily")
    scheduler.add_job(run_monthly_komponen_retail, "cron", day=1, hour=4, id="komponen-retail-monthly", max_instances=1)
    print("HargaPas scheduler aktif: weekly e-commerce + daily Facebook + monthly anchor komponen retail (tgl 1)")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    main()
