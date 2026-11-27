"""Start the hosted demo, for example in a container.

Required environment variables:

    ARM_DEMO_DATA                 folder on a persistent disk, for the memories
    ARM_AUTH_REDIRECT_URI         https://<your address>/oauth2callback
    ARM_AUTH_COOKIE_SECRET        a long random string
    ARM_AUTH_GOOGLE_CLIENT_ID     from a Google OAuth client of type "Web application"
    ARM_AUTH_GOOGLE_CLIENT_SECRET

Optional: OPENROUTER_API_KEY (without it the assistant is off), PORT, and the limits read
in ``demo/hosting.py``.

It refuses to start unless sign-in is configured, writes Streamlit's secrets file from the
variables, and, when run as root, gives up root before starting the app.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRETS = ROOT / ".streamlit" / "secrets.toml"
APP_USER = 10001
REQUIRED = (
    "ARM_DEMO_DATA",
    "ARM_AUTH_REDIRECT_URI",
    "ARM_AUTH_COOKIE_SECRET",
    "ARM_AUTH_GOOGLE_CLIENT_ID",
    "ARM_AUTH_GOOGLE_CLIENT_SECRET",
)
GOOGLE_METADATA = "https://accounts.google.com/.well-known/openid-configuration"


def secrets_toml(env) -> str:
    """Streamlit's ``[auth]`` settings. JSON strings are valid TOML strings."""
    quote = json.dumps
    return "\n".join(
        [
            "[auth]",
            f"redirect_uri = {quote(env['ARM_AUTH_REDIRECT_URI'])}",
            f"cookie_secret = {quote(env['ARM_AUTH_COOKIE_SECRET'])}",
            "",
            "[auth.google]",
            f"client_id = {quote(env['ARM_AUTH_GOOGLE_CLIENT_ID'])}",
            f"client_secret = {quote(env['ARM_AUTH_GOOGLE_CLIENT_SECRET'])}",
            f"server_metadata_url = {quote(GOOGLE_METADATA)}",
            "",
        ]
    )


def missing(env) -> list[str]:
    return [name for name in REQUIRED if not env.get(name)]


def drop_root(data_dir: Path) -> None:
    for path in [data_dir, *data_dir.rglob("*"), SECRETS]:
        os.chown(path, APP_USER, APP_USER)
    os.setgroups([])
    os.setgid(APP_USER)
    os.setuid(APP_USER)
    os.environ["HOME"] = "/home/app"


def main() -> None:
    absent = missing(os.environ)
    if absent:
        sys.exit(f"not starting: set {', '.join(absent)}")
    os.environ["ARM_DEMO_HOSTED"] = "1"
    data_dir = Path(os.environ["ARM_DEMO_DATA"])
    data_dir.mkdir(parents=True, exist_ok=True)
    SECRETS.parent.mkdir(parents=True, exist_ok=True)
    SECRETS.touch(mode=0o600)
    SECRETS.chmod(0o600)
    SECRETS.write_text(secrets_toml(os.environ))
    if os.getuid() == 0:
        drop_root(data_dir)
    os.chdir(ROOT)
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "demo/app.py",
            "--server.headless=true",
            "--server.address=0.0.0.0",
            f"--server.port={os.environ.get('PORT', '8501')}",
        ],
    )


if __name__ == "__main__":
    main()
