import json
import uuid

import stripe
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.models import UserSubscription
from core.services.payments.stripe_gateway import list_customer_subscriptions


REMOTE_STATUS_MAP = {
    "active": "active",
    "trialing": "active",
    "past_due": "past_due",
    "canceled": "canceled",
    "unpaid": "failed",
    "incomplete": "pending",
    "incomplete_expired": "expired",
    "paused": "failed",
}


class Command(BaseCommand):
    help = (
        "Read-only audit comparing Stripe subscriptions with local Ibda "
        "subscription rows for one owner or Stripe customer. It never "
        "cancels, updates, deletes, or reconciles anything."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--owner-id",
            default="",
            help="Supabase user UUID whose local subscription rows to audit.",
        )
        parser.add_argument(
            "--customer-id",
            action="append",
            default=[],
            help="Stripe customer ID to audit (repeatable).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print the complete report as JSON.",
        )

    def handle(self, *args, **options):
        if not getattr(settings, "STRIPE_SECRET_KEY", "").strip():
            raise CommandError(
                "STRIPE_SECRET_KEY is not configured; the audit cannot "
                "query Stripe. No changes were made."
            )

        owner_id = None
        if options["owner_id"]:
            try:
                owner_id = uuid.UUID(str(options["owner_id"]))
            except (ValueError, TypeError, AttributeError) as error:
                raise CommandError(
                    "--owner-id must be a valid Supabase user UUID."
                ) from error

        explicit_customers = sorted(
            {value.strip() for value in options["customer_id"] if value.strip()}
        )
        if owner_id is None and not explicit_customers:
            raise CommandError(
                "Provide --owner-id or at least one --customer-id."
            )

        local_rows = list(
            UserSubscription.objects.filter(
                **(
                    {"owner_id": owner_id}
                    if owner_id is not None
                    else {"provider_customer_id__in": explicit_customers}
                )
            ).order_by("-created_at")
        )

        customer_ids = set(explicit_customers)
        for row in local_rows:
            if row.provider_customer_id:
                customer_ids.add(row.provider_customer_id)

        remote_by_id = {}
        for customer_id in sorted(customer_ids):
            try:
                remote_subscriptions = list_customer_subscriptions(customer_id)
            except stripe.StripeError as error:
                raise CommandError(
                    "Stripe subscription lookup failed "
                    f"(error type {type(error).__name__}). No changes were made."
                ) from error
            for subscription in remote_subscriptions:
                subscription_id = getattr(subscription, "id", "")
                if subscription_id:
                    remote_by_id[subscription_id] = subscription

        local_subscription_ids = {
            row.provider_subscription_id
            for row in local_rows
            if row.provider_subscription_id
        }

        local_report = []
        for row in local_rows:
            remote = remote_by_id.get(row.provider_subscription_id or "")
            remote_status = getattr(remote, "status", None) if remote else None
            remote_customer_id = (
                self._identifier(getattr(remote, "customer", None))
                if remote
                else None
            )
            issues = []
            if not row.provider_subscription_id:
                issues.append("missing_remote_subscription_id")
            elif remote is None:
                issues.append("remote_subscription_not_found")
            else:
                if (
                    remote_customer_id
                    and row.provider_customer_id
                    and remote_customer_id != row.provider_customer_id
                ):
                    issues.append("customer_mismatch")
                expected_local_status = REMOTE_STATUS_MAP.get(remote_status)
                if expected_local_status and expected_local_status != row.status:
                    issues.append("status_mismatch")
            local_report.append(
                {
                    "id": str(row.id),
                    "owner_id": str(row.owner_id),
                    "provider": row.provider,
                    "local_status": row.status,
                    "plan_id": row.plan_id,
                    "billing_interval": row.billing_interval,
                    "provider_customer_id": row.provider_customer_id or None,
                    "provider_subscription_id": (
                        row.provider_subscription_id or None
                    ),
                    "remote_status": remote_status,
                    "issues": issues,
                }
            )

        remote_report = []
        status_counts = {}
        for subscription in remote_by_id.values():
            subscription_id = getattr(subscription, "id", "")
            authenticated_status = getattr(subscription, "status", None) or (
                "unknown"
            )
            status_counts[authenticated_status] = (
                status_counts.get(authenticated_status, 0) + 1
            )
            remote_report.append(
                {
                    "id": subscription_id,
                    "customer_id": self._identifier(
                        getattr(subscription, "customer", None)
                    ),
                    "status": getattr(subscription, "status", None),
                    "cancel_at_period_end": bool(
                        getattr(subscription, "cancel_at_period_end", False)
                    ),
                    "current_period_end": getattr(
                        subscription, "current_period_end", None
                    ),
                    "local_subscription_id": next(
                        (
                            str(row.id)
                            for row in local_rows
                            if row.provider_subscription_id == subscription_id
                        ),
                        None,
                    ),
                    "orphaned": subscription_id not in local_subscription_ids,
                }
            )

        report = {
            "read_only": True,
            "owner_id": str(owner_id) if owner_id is not None else None,
            "customer_ids": sorted(customer_ids),
            "remote_status_counts": status_counts,
            "local_subscriptions": local_report,
            "remote_subscriptions": remote_report,
            "orphaned_remote_subscriptions": [
                item["id"] for item in remote_report if item["orphaned"]
            ],
            "local_rows_without_remote_subscription": [
                item["id"]
                for item in local_report
                if "remote_subscription_not_found"
                in item["issues"]
            ],
            "local_rows_missing_remote_id": [
                item["id"]
                for item in local_report
                if "missing_remote_subscription_id" in item["issues"]
            ],
            "customer_or_status_mismatches": [
                item["id"]
                for item in local_report
                if "customer_mismatch" in item["issues"]
                or "status_mismatch" in item["issues"]
            ],
        }
        if not customer_ids:
            report["note"] = (
                "No Stripe customer ID is stored on the matching local rows; "
                "there is nothing to compare remotely. If the owner has a "
                "remote subscription, re-run with --customer-id."
            )

        if options["json"]:
            self.stdout.write(
                json.dumps(report, indent=2, sort_keys=True, default=str)
            )
            return

        self.stdout.write("Stripe subscription audit (read-only; no changes)")
        self.stdout.write(
            f"Owner: {report['owner_id'] or 'not specified (customer mode)'}"
        )
        self.stdout.write(
            "Customers: " + (", ".join(report["customer_ids"]) or "none")
        )
        self.stdout.write(
            "Remote status counts: "
            + (
                ", ".join(
                    f"{key}={value}"
                    for key, value in sorted(status_counts.items())
                )
                or "none"
            )
        )
        self.stdout.write(f"Local rows: {len(local_report)}")
        for item in local_report:
            self.stdout.write(
                "  local id={id} owner={owner_id} local_status={local_status} "
                "remote_status={remote_status} customer={provider_customer_id} "
                "remote_id={provider_subscription_id} issues={issues}".format(
                    issues=",".join(item["issues"]) or "none",
                    **item,
                )
            )
        self.stdout.write(f"Remote subscriptions: {len(remote_report)}")
        for item in remote_report:
            self.stdout.write(
                "  remote id={id} status={status} customer={customer_id} "
                "local_subscription_id={local_subscription_id} "
                "orphaned={orphaned}".format(**item)
            )
        self.stdout.write(
            "Orphaned remote subscriptions: "
            + (", ".join(report["orphaned_remote_subscriptions"]) or "none")
        )
        self.stdout.write(
            "Local rows without a remote subscription: "
            + (
                ", ".join(report["local_rows_without_remote_subscription"])
                or "none"
            )
        )
        self.stdout.write(
            "Local rows missing a remote subscription ID: "
            + (", ".join(report["local_rows_missing_remote_id"]) or "none")
        )
        self.stdout.write(
            "Customer/status mismatches: "
            + (", ".join(report["customer_or_status_mismatches"]) or "none")
        )
        if "note" in report:
            self.stdout.write(report["note"])

    @staticmethod
    def _identifier(value):
        if isinstance(value, str):
            return value
        return getattr(value, "id", None)
