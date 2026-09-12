import time

from app.config import settings
from app.connectors import queue_due_connectors


def main():
    interval = max(settings().connector_scheduler_interval_seconds, 30)
    while True:
        try:
            queue_due_connectors()
        except Exception as exc:
            print(f"connector scheduler error: {exc}", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    main()
