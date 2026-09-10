"""Provision the non-owner runtime role, then run reviewed schema migrations."""

import os
import subprocess

import psycopg
from dotenv import load_dotenv
from psycopg import sql
from rushes.config import settings

load_dotenv()
with psycopg.connect(
    settings().require_admin_database_url().get_secret_value().replace("+psycopg", ""),
    autocommit=True,
) as connection:
    if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname = 'rushes_app'").fetchone():
        connection.execute(
            sql.SQL(
                "CREATE ROLE rushes_app LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
            ).format(sql.Literal(os.environ["RUSHES_APP_PASSWORD"]))
        )
subprocess.run(["alembic", "upgrade", "head"], check=True)
print("Database migrated; runtime role has no RLS bypass or schema ownership.")
