"""Build exported pages using the same public configuration as the local application."""

import os
import subprocess
from pathlib import Path

from rushes.config import settings

if __name__ == "__main__":
    subprocess.run(
        ["npm", "run", "build"],
        cwd=Path(__file__).resolve().parents[1] / "web",
        env={
            **os.environ,
            **{"RUSHES_" + key.upper(): value for key, value in settings().public_web_config.items()},
        },
        check=True,
    )
