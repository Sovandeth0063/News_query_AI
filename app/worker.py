import logging
import time
from apscheduler.schedulers.background import BackgroundScheduler
from app.config import settings
from app.sync_manager import sync_manager
from app.storage.database import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("Worker")

scheduler = None

def scheduled_job():
    logger.info("Triggering scheduled daily news ingestion...")
    run_id = sync_manager.run_sync_background(trigger="schedule")
    logger.info(f"Ingestion run started: {run_id}")

def start_worker():
    global scheduler
    init_db()
    logger.info("Initializing APScheduler worker...")
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        scheduled_job,
        'interval',
        hours=settings.INGEST_INTERVAL_HOURS,
        id='daily_news_sync',
        replace_existing=True
    )
    scheduler.start()
    logger.info(f"Scheduler started. News will be refreshed every {settings.INGEST_INTERVAL_HOURS} hours.")

def stop_worker():
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler shutdown cleanly.")

if __name__ == "__main__":
    start_worker()
    print(f"Worker running (interval: {settings.INGEST_INTERVAL_HOURS}h). Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        stop_worker()
