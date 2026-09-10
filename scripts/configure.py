"""Generate local development configuration without displaying credentials."""

import os
import secrets
from pathlib import Path


def main():
    target = Path(".env")
    admin = secrets.token_hex(24)
    app = secrets.token_hex(24)
    content = Path(".env.example").read_text()
    content = content.replace("rushes_app:GENERATE", f"rushes_app:{app}")
    content = content.replace("rushes_admin:GENERATE", f"rushes_admin:{admin}")
    content = content.replace("POSTGRES_PASSWORD=GENERATE", f"POSTGRES_PASSWORD={admin}")
    content = content.replace("RUSHES_APP_PASSWORD=GENERATE", f"RUSHES_APP_PASSWORD={app}")
    content = content.replace("RUSHES_SECRET=GENERATE", f"RUSHES_SECRET={secrets.token_hex(32)}")
    try:
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        print("Existing .env preserved.")
        return
    with os.fdopen(fd, "w") as file:
        file.write(content)
    print("Created private .env with generated local credentials.")


if __name__ == "__main__":
    main()
