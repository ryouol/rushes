"""Apply pinned Temporal schemas to explicitly provisioned, separate databases."""

import os
import subprocess
from pathlib import Path

import psycopg
from rushes.config import settings
from rushes.workflow_service import database_tls, database_urls


def main():
    root = Path(os.environ.get("RUSHES_TEMPORAL_SERVER_ROOT", "/opt/temporal"))
    for name, url in zip(("temporal", "visibility"), database_urls(settings()), strict=True):
        tls = database_tls(url)
        env = {
            **os.environ,
            "SQL_PLUGIN": "postgres12",
            "SQL_HOST": url.host,
            "SQL_PORT": str(url.port or 5432),
            "SQL_USER": url.username,
            "SQL_PASSWORD": url.password,
            "SQL_DATABASE": url.database,
            "SQL_TLS": str(tls["enabled"]).lower(),
            "SQL_TLS_SERVER_NAME": tls["serverName"],
            "SQL_TLS_CA_FILE": tls["caFile"],
            "SQL_TLS_DISABLE_HOST_VERIFICATION": str(not tls["enableHostVerification"]).lower(),
        }
        query = {"sslmode": url.query.get("sslmode", "verify-full")}
        if query["sslmode"] == "verify-full":
            query["sslrootcert"] = url.query.get("sslrootcert", "system")
        connection_url = url.set(drivername="postgresql", query=query)
        with psycopg.connect(connection_url.render_as_string(hide_password=False)) as db:
            initialized = (
                db.execute("SELECT to_regclass('public.schema_version')").fetchone()[0] is not None
            )
        tool = str(root / "temporal-sql-tool")
        if not initialized:
            subprocess.run([tool, "setup-schema", "--version", "0.0"], env=env, check=True)
        subprocess.run(
            [tool, "update-schema", "--schema-dir", str(root / "schema" / name / "versioned")],
            env=env,
            check=True,
        )
    print(
        "Temporal workflow and visibility schemas are current; application tables were not modified"
    )


if __name__ == "__main__":
    main()
