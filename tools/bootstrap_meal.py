"""Administrative CLI utility to provision meals and invite participants.

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


def main():
    parser = argparse.ArgumentParser(description="Provision a new SettleTable meal room administratively")
    parser.add_argument("--meal-id", required=True, help="Unique identifier for the meal room (e.g. friday-dinner)")
    parser.add_argument("--organizer", default="Organizer", help="Display name of the meal organizer (default: Organizer)")
    parser.add_argument("--diners", default="", help="Comma-separated list of diner display names (e.g. Alice,Bob,Charlie)")
    parser.add_argument("--db", default=os.environ.get("SETTLETABLE_DB_PATH", ".local/settletable.sqlite"),
                        help="Path to the SQLite database")
    parser.add_argument("--origin", default=os.environ.get("SETTLETABLE_SERVER_ORIGIN", "http://localhost:8000"),
                        help="Public base URL of the SettleTable application")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    origin = args.origin.rstrip("/")

    # Construct participants tuple
    participants = [Participant(id="O", name=args.organizer.strip(), organizer=True)]
    if args.diners.strip():
        for idx, diner_name in enumerate(args.diners.split(","), start=1):
            clean = diner_name.strip()
            if clean:
                participants.append(Participant(id=f"D{idx}", name=clean, organizer=False))

    authority = Authority(db_path)
    try:
        res = authority.bootstrap(args.meal_id, tuple(participants))
        org_session = next(s for s, p in zip(res.sessions, participants) if p.organizer)

        print("\n" + "=" * 65)
        print(" SettleTable -- Meal Provisioning Successful")
        print("=" * 65)
        print(f" Meal ID:       {res.meal_id}")
        print(f" Database:      {db_path}")
        print(f" Organizer:     {args.organizer} (ID: {org_session.participant_id})")
        print(f"\n Organizer Session Credential:")
        print(f"   {org_session.credential}")
        print(f"\n Web Entry URL (Set Cookie or Direct Link):")
        print(f"   {origin}/#/meal/{res.meal_id}")

        # Pre-generate invitations for predeclared diners
        if len(participants) > 1:
            print(f"\n Diner Invitation Links:")
            for p in participants:
                if not p.organizer:
                    inv = authority.issue_invitation(org_session.credential, res.meal_id, p.id)
                    print(f"   - {p.name:<12} (ID: {p.id}): {origin}/invite/{inv.token}")

        print(f"\n General Join Link (Requires Organizer Approval):")
        print(f"   {origin}/join/{res.meal_id}")
        print("=" * 65 + "\n")
    except Exception as e:
        print(f"[ERROR] Failed to bootstrap meal: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        authority.close()


if __name__ == "__main__":
    main()
