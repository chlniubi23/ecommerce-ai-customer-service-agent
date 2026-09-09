from __future__ import annotations

import argparse
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database.connection import mysql_connection  # noqa: E402


TABLES = [
    "workflow_runtime_records",
    "agent_audit_logs",
    "supervisor_escalations",
    "human_agent_status",
    "complaint_escalations",
    "complaint_process_records",
    "complaints",
    "refunds",
    "logistics_tracking_events",
    "logistics_shipments",
    "carriers",
    "order_items",
    "orders",
    "inventory_history",
    "inventory",
    "product_collection_items",
    "product_images",
    "products",
    "product_collections",
    "categories",
    "brands",
    "user_addresses",
    "users",
]


def reset_business_data(dry_run: bool = False) -> None:
    if dry_run:
        print("Tables that would be truncated:")
        for table in TABLES:
            print(f"- {table}")
        return

    with mysql_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
            for table in TABLES:
                cursor.execute(f"TRUNCATE TABLE {table}")
                print(f"truncated {table}")
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset commerce business data while preserving schema.")
    parser.add_argument("--dry-run", action="store_true", help="Print target tables without truncating them.")
    parser.add_argument("--yes", action="store_true", help="Required confirmation for destructive reset.")
    args = parser.parse_args()

    if not args.dry_run and not args.yes:
        print("Refusing to reset data without --yes. Use --dry-run to inspect target tables.")
        return 2

    reset_business_data(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
