"""
Create the first operator account, and any later one from the command line.

There is no sign-up, by design: an account here is permission to read other
people's welfare applications, and it is granted by somebody who knows who is
being granted it. `/api/operator/accounts` enforces that by requiring an admin.

Which leaves a chicken and an egg. The first admin cannot be created through a
route that requires an admin, so it is created here — by somebody who already
has the database, which is a fair proxy for "is allowed to decide this".

    python scripts/create_operator.py --org "Patna CSC" --kind CSC \\
        --email you@example.org --name "Your Name" --role admin

The password is read from a prompt and never from an argument. A password in
argv is in your shell history, in `ps` output, and in the terminal scrollback
somebody else can read over your shoulder.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import auth                                          # noqa: E402
from src.database import (create_operator, create_organisation,   # noqa: E402
                          find_operator_by_email, get_connection,
                          init_database)

MINIMUM = 12


async def run(args: argparse.Namespace) -> int:
    password = getpass.getpass("Password (not echoed): ")
    if len(password) < MINIMUM:
        print(f"Too short — {MINIMUM} characters minimum. Length is what "
              f"resists guessing; composition rules just produce Password1!")
        return 1
    if password != getpass.getpass("Again: "):
        print("They do not match.")
        return 1

    await init_database()
    db = await get_connection()
    try:
        if await find_operator_by_email(db, args.email):
            print(f"An account already exists for {args.email.lower()}.")
            return 1

        organisation_id = args.org_id or uuid.uuid4().hex
        if not args.org_id:
            await create_organisation(db, organisation_id, args.org, args.kind,
                                      args.state, args.district)

        operator_id = uuid.uuid4().hex
        await create_operator(db, operator_id, organisation_id,
                              args.email, args.name,
                              auth.hash_password(password), args.role)
    finally:
        await db.close()

    print(f"\n  operator     {operator_id}")
    print(f"  organisation {organisation_id}")
    print(f"  email        {args.email.lower()}")
    print(f"  role         {args.role}")
    print("\nSign in at /operator. An admin can create the rest from there.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", default="admin", choices=list(auth.ROLES))
    parser.add_argument("--org", default="", help="Name of a NEW organisation")
    parser.add_argument("--kind", default="CSC",
                        choices=["CSC", "NGO", "SCA", "BANK"])
    parser.add_argument("--state", default=None)
    parser.add_argument("--district", default=None)
    parser.add_argument("--org-id", default="",
                        help="Join an EXISTING organisation instead")
    args = parser.parse_args()

    if not (args.org or args.org_id):
        parser.error("give --org to create one, or --org-id to join one")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
