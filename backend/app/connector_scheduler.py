import time

from app.config import settings
from app.connectors import queue_due_connectors
from app.memory_agent import queue_due_scans
from app.dream_lab import queue_due_dreams
from app.licensing import require_commercial_license


def main():
    interval = max(settings().connector_scheduler_interval_seconds, 30)
    while True:
        try:
            require_commercial_license()
            queue_due_connectors()
            queue_due_scans()
            queue_due_dreams()
        except Exception as exc:
            print(f"connector scheduler error: {exc}", flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    main()
