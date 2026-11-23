"""One-time interactive login. Saves tokens so the server never needs your password."""

from __future__ import annotations

import getpass

from garminconnect import Garmin

from garmin_mcp.client import token_dir


def main() -> None:
    email = input("Garmin email: ").strip()
    password = getpass.getpass("Garmin password: ")
    path = token_dir()
    path.mkdir(parents=True, exist_ok=True)
    client = Garmin(email, password, prompt_mfa=lambda: input("MFA code: ").strip())
    client.login(str(path))
    print(f"Logged in. Session tokens saved to {path}")


if __name__ == "__main__":
    main()
