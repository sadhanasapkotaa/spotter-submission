"""Create envs/<env>.env from its example. Non-local envs get random secrets."""

import re
import secrets
import sys
from pathlib import Path


def main(env: str) -> None:
    envs = Path(__file__).resolve().parent.parent / "envs"
    target = envs / f"{env}.env"
    if target.exists():
        return
    text = (envs / f"{env}.env.example").read_text()
    if env != "local":
        text = text.replace(f"spotter_{env}_pw", secrets.token_hex(16))
        text = re.sub(
            r"(?m)^DJANGO_SECRET_KEY=.*$",
            f"DJANGO_SECRET_KEY={secrets.token_urlsafe(50)}",
            text,
        )
    target.write_text(text)
    print(f"created {target.relative_to(envs.parent)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "local")
