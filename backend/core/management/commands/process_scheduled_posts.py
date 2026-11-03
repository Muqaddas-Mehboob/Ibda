import json
import time

from django.core.management.base import BaseCommand

from core.services.scheduling import publish_due_posts


class Command(BaseCommand):
    help = (
        "Process due scheduled posts. Run once from cron/Task Scheduler, or "
        "with --loop for a long-lived worker process."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Keep running instead of processing a single batch.",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=60,
            help="Seconds to sleep between batches when --loop is used.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=25,
            help="Maximum posts claimed per batch.",
        )

    def handle(self, *args, **options):
        limit = max(1, options["limit"])

        if not options["loop"]:
            self._report(publish_due_posts(limit=limit))
            return

        interval = max(5, options["interval"])
        self.stdout.write(
            f"Scheduler loop started (interval={interval}s, limit={limit})."
        )
        try:
            while True:
                self._report(publish_due_posts(limit=limit))
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write("Scheduler loop stopped.")

    def _report(self, counts):
        self.stdout.write(json.dumps(counts))
