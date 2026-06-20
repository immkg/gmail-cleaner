import argparse

from .db import init_db, get_state
from .auth import get_gmail_service
from .sync import full_sync, incremental_sync
from .analyze import run_analysis
from .delete import run_delete_flow


def sync_command(args):
    conn = init_db()
    history_id = get_state(conn, "history_id")

    if history_id is None:
        full_sync(conn)
    else:
        incremental_sync(conn, history_id)

    total = conn.execute("SELECT COUNT(*) FROM gmail_messages").fetchone()[0]
    print(f"\nDatabase now contains {total:,} emails")
    conn.close()


def analyze_command(args):
    run_analysis()


def clean_command(args):
    run_delete_flow(dry_run=args.dry_run)


def main():
    parser = argparse.ArgumentParser(
        description="Gmail Sync and Analysis Tool")
    subparsers = parser.add_subparsers(title="commands", dest="command")
    subparsers.required = True

    # Sync
    parser_sync = subparsers.add_parser(
        "sync", help="Synchronize emails from Gmail to local DB")
    parser_sync.set_defaults(func=sync_command)

    # Analyze
    parser_analyze = subparsers.add_parser(
        "analyze", help="Analyze downloaded emails and show statistics")
    parser_analyze.set_defaults(func=analyze_command)

    # Clean
    parser_clean = subparsers.add_parser("clean", help="Interactive CLI to bulk delete emails")
    parser_clean.add_argument("--dry-run", action="store_true", help="Simulate deletion without calling Gmail API")
    parser_clean.set_defaults(func=clean_command)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
