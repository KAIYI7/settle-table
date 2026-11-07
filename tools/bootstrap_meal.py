"""Administrative CLI utility to provision meals, generate organizer setup links, and recover access.

Because `POST /api/meals/{meal_id}/bootstrap` is strictly restricted to
loopback and rejected when proxy headers are present, this CLI tool allows
administrators and self-hosters to provision meals directly on the host
without exposing the bootstrap endpoint to the public Internet.
"""
import argparse
import os
from pathlib import Path
import sys

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from settletable.authority import Authority, Participant


def run_bootstrap(meal_id: str, organizer_name: str, diners_str: str, db_path: Path, origin: str, session_ttl: int = 604800):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    origin = origin.rstrip("/")

    # Construct participants tuple
    participants = [Participant(id="O", name=organizer_name.strip(), organizer=True)]
    if diners_str.strip():
        for idx, diner_name in enumerate(diners_str.split(","), start=1):
            clean = diner_name.strip()
            if clean:
                participants.append(Participant(id=f"D{idx}", name=clean, organizer=False))

    authority = Authority(db_path)
    try:
        res = authority.bootstrap(meal_id, tuple(participants), session_ttl=session_ttl)
        org_session = next(s for s, p in zip(res.sessions, participants) if p.organizer)

        print("\n" + "=" * 65)
        print(" SettleTable -- Meal Provisioning Successful")
        print("=" * 65)
        print(f" Meal ID:       {res.meal_id}")
        print(f" Database:      {db_path}")
        print(f" Organizer:     {organizer_name} (ID: {org_session.participant_id})")

        if res.organizer_claim:
            print(f"\n Organizer Browser Setup Link (Single-Use, contains ephemeral claim secret):")
            print(f"   {origin}/#/claim-organizer/{res.organizer_claim.token}")
            print("   (Open this link once in your browser to activate your organizer session)")

        # Pre-generate invitations for predeclared diners
        if len(participants) > 1:
            print(f"\n Diner Invitation Links:")
            for p in participants:
                if not p.organizer:
                    inv = authority.issue_invitation(org_session.credential, res.meal_id, p.id, invite_ttl=session_ttl)
                    print(f"   - {p.name:<12} (ID: {p.id}): {origin}/#/invite/{inv.token}")

        print(f"\n General Join Link (Requires Organizer Approval):")
        print(f"   {origin}/join/{res.meal_id}")
        print("=" * 65 + "\n")
    finally:
        authority.close()


def run_recover(meal_id: str, db_path: Path, origin: str, claim_ttl: int = 604800):
    if not db_path.exists():
        print(f"[ERROR] Database file not found: {db_path}", file=sys.stderr)
        sys.exit(1)
    origin = origin.rstrip("/")

    authority = Authority(db_path)
    try:
        grant = authority.issue_organizer_claim(meal_id, claim_ttl=claim_ttl)
        inspection = authority.inspect_organizer_claim(grant.token)

        print("\n" + "=" * 65)
        print(" SettleTable -- Emergency Organizer Recovery")
        print("=" * 65)
        print(f" Meal ID:       {meal_id}")
        print(f" Database:      {db_path}")
        print(f" Organizer:     {inspection.organizer_name or 'Organizer'} (ID: {inspection.organizer_id or 'O'})")
        print(f"\n Organizer Recovery Link (Single-Use, contains ephemeral claim secret; valid for {claim_ttl // 86400} days):")
        print(f"   {origin}/#/claim-organizer/{grant.token}")
        print("   (Open this link once in your browser to restore organizer access)")
        print("=" * 65 + "\n")
    finally:
        authority.close()


def main():
    parser = argparse.ArgumentParser(description="Provision a new SettleTable meal room or recover organizer access administratively")
    subparsers = parser.add_subparsers(dest="command")

    # Bootstrap subcommand
    boot_parser = subparsers.add_parser("bootstrap", help="Provision a new meal room")
    boot_parser.add_argument("--meal-id", required=True, help="Unique identifier for the meal room (e.g. friday-dinner)")
    boot_parser.add_argument("--organizer", default="Organizer", help="Display name of the meal organizer (default: Organizer)")
    boot_parser.add_argument("--diners", default="", help="Comma-separated list of diner display names (e.g. Alice,Bob,Charlie)")
    boot_parser.add_argument("--session-ttl", type=int, default=604800, help="Session TTL in seconds (default: 604800 / 7 days)")
    boot_parser.add_argument("--db", default=os.environ.get("SETTLETABLE_DB_PATH", ".local/settletable.sqlite"),
                             help="Path to the SQLite database")
    boot_parser.add_argument("--origin", default=os.environ.get("SETTLETABLE_SERVER_ORIGIN", "http://localhost:8000"),
                             help="Public base URL of the SettleTable application")

    # Recover subcommand
    rec_parser = subparsers.add_parser("recover", help="Generate a fresh single-use organizer recovery link")
    rec_parser.add_argument("--meal-id", required=True, help="Unique identifier for the meal room to recover")
    rec_parser.add_argument("--claim-ttl", type=int, default=604800, help="Recovery link TTL in seconds (default: 604800 / 7 days)")
    rec_parser.add_argument("--db", default=os.environ.get("SETTLETABLE_DB_PATH", ".local/settletable.sqlite"),
                            help="Path to the SQLite database")
    rec_parser.add_argument("--origin", default=os.environ.get("SETTLETABLE_SERVER_ORIGIN", "http://localhost:8000"),
                            help="Public base URL of the SettleTable application")

    # Root fallback arguments for backwards compatibility when no subcommand is specified
    parser.add_argument("--meal-id", help="Unique identifier for the meal room (fallback for direct bootstrap)")
    parser.add_argument("--organizer", default="Organizer", help="Display name of the meal organizer")
    parser.add_argument("--diners", default="", help="Comma-separated list of diner display names")
    parser.add_argument("--session-ttl", type=int, default=604800, help="Session TTL in seconds")
    parser.add_argument("--db", default=os.environ.get("SETTLETABLE_DB_PATH", ".local/settletable.sqlite"),
                        help="Path to the SQLite database")
    parser.add_argument("--origin", default=os.environ.get("SETTLETABLE_SERVER_ORIGIN", "http://localhost:8000"),
                        help="Public base URL of the SettleTable application")

    args = parser.parse_args()

    try:
        if args.command == "recover":
            db_path = Path(args.db).resolve()
            run_recover(args.meal_id, db_path, args.origin, claim_ttl=args.claim_ttl)
        elif args.command == "bootstrap" or args.meal_id:
            db_path = Path(args.db).resolve()
            run_bootstrap(args.meal_id, args.organizer, args.diners, db_path, args.origin, session_ttl=args.session_ttl)
        else:
            parser.print_help()
            sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Operation failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
