"""Command line for the things that have no screen.

Accounts are created here rather than in the browser on purpose: an
open sign-up page on a tool holding driver Social Security numbers would be
the wrong default, and whoever installs the desk already has a terminal open.

    python -m app.cli create-user
    python -m app.cli list-users
    python -m app.cli set-password dana
    python -m app.cli disable-user dana
"""

from __future__ import annotations

import argparse
import getpass
import secrets
import sys

from sqlalchemy import select

from app.database import create_all, get_session_factory
from app.models import User
from app.services import auth


def _prompt_password(confirm: bool = True) -> str:
    while True:
        password = getpass.getpass("Password: ")
        if len(password) < auth.MIN_PASSWORD_LENGTH:
            print(
                f"  Too short — at least {auth.MIN_PASSWORD_LENGTH} characters.",
                file=sys.stderr,
            )
            continue
        if confirm and password != getpass.getpass("Password again: "):
            print("  Those did not match. Try again.", file=sys.stderr)
            continue
        return password


def create_user(args: argparse.Namespace) -> int:
    create_all()
    with get_session_factory()() as session:
        username = args.username or input("Username: ")

        display = args.display_name
        if display is None:
            # Supplying --password means this is being driven by a script,
            # so do not stop to ask for something optional.
            display = "" if args.password else input(
                "Full name (shown in the app, optional): "
            )

        password = args.password or _prompt_password()

        try:
            user = auth.create_user(
                session,
                username=username,
                password=password,
                display_name=display or "",
            )
        except (ValueError, auth.PasswordTooShort) as error:
            print(f"\n  {error}\n", file=sys.stderr)
            return 1

        session.commit()
        print(f"\n  Created the account “{user.username}”.")
        print("  Everyone now needs to sign in, including on this machine.\n")
    return 0


def list_users(_: argparse.Namespace) -> int:
    create_all()
    with get_session_factory()() as session:
        users = session.scalars(select(User).order_by(User.created_at)).all()
        if not users:
            print("\n  No accounts. The desk runs without a login, on this")
            print("  machine only.\n")
            return 0
        print()
        for user in users:
            state = "" if user.is_active else "  (disabled)"
            seen = (
                user.last_login_at.strftime("%Y-%m-%d %H:%M")
                if user.last_login_at
                else "never"
            )
            print(f"  {user.username:<20} {user.display_name:<24} last seen {seen}{state}")
        print()
    return 0


def set_password(args: argparse.Namespace) -> int:
    create_all()
    with get_session_factory()() as session:
        user = auth.get_user(session, args.username)
        if user is None:
            print(f"\n  No account called “{args.username}”.\n", file=sys.stderr)
            return 1
        try:
            auth.set_password(session, user, args.password or _prompt_password())
        except auth.PasswordTooShort as error:
            print(f"\n  {error}\n", file=sys.stderr)
            return 1
        session.commit()
        print(f"\n  Password changed. {user.username} has been signed out everywhere.\n")
    return 0


def disable_user(args: argparse.Namespace) -> int:
    create_all()
    with get_session_factory()() as session:
        user = auth.get_user(session, args.username)
        if user is None:
            print(f"\n  No account called “{args.username}”.\n", file=sys.stderr)
            return 1
        active = session.scalars(select(User).where(User.is_active.is_(True))).all()
        if len(active) <= 1 and user.is_active:
            print(
                "\n  That is the only account left. Disabling it would lock"
                "\n  everyone out. Create another one first.\n",
                file=sys.stderr,
            )
            return 1
        user.is_active = False
        # Replace the password with something unusable, so a disabled
        # account cannot be signed into even if it is re-enabled by hand.
        auth.set_password(session, user, secrets.token_urlsafe(32))
        session.commit()
        print(f"\n  {user.username} is disabled and signed out.\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Manage who can use the contract desk.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("create-user", help="add an account")
    new.add_argument("username", nargs="?")
    new.add_argument("--display-name", default=None)
    new.add_argument("--password", default=None, help="skips the prompt; avoid in shared shell history")
    new.set_defaults(func=create_user)

    listing = sub.add_parser("list-users", help="show the accounts")
    listing.set_defaults(func=list_users)

    passwd = sub.add_parser("set-password", help="change a password")
    passwd.add_argument("username")
    passwd.add_argument("--password", default=None)
    passwd.set_defaults(func=set_password)

    off = sub.add_parser("disable-user", help="stop an account signing in")
    off.add_argument("username")
    off.set_defaults(func=disable_user)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n  Cancelled.\n", file=sys.stderr)
        return 130
    except EOFError:
        # Reached when a prompt is hit with no terminal attached.
        print(
            "\n  This needs a terminal to ask for the details."
            "\n  Pass them as arguments instead, for example:"
            "\n      python -m app.cli create-user dana --display-name \"Dana Okafor\"\n",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
