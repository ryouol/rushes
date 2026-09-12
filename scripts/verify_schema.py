"""Verify fresh migrations in a generated disposable database, then remove only that database."""

import json
import os
import subprocess
import uuid
from pathlib import Path

import psycopg
from psycopg import sql
from rushes.config import settings
from sqlalchemy.engine import make_url


def main():
    admin = make_url(settings().require_admin_database_url().get_secret_value())
    name = f"rushes_schema_test_{uuid.uuid4().hex}"
    url = admin.set(database=name)
    with psycopg.connect(
        admin.render_as_string(hide_password=False).replace("+psycopg", ""), autocommit=True
    ) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            env = {
                **os.environ,
                "RUSHES_ADMIN_DATABASE_URL": url.render_as_string(hide_password=False),
            }
            subprocess.run(["alembic", "upgrade", "head"], env=env, check=True)
            with psycopg.connect(
                url.render_as_string(hide_password=False).replace("+psycopg", "")
            ) as db:
                version = db.execute("SELECT version_num FROM alembic_version").fetchone()[0]
                forced = db.execute(
                    "SELECT count(*) FROM pg_class WHERE relrowsecurity AND relforcerowsecurity AND relnamespace = 'public'::regnamespace"
                ).fetchone()[0]
                assert forced == 17
                assert version == "0008"
                assert db.execute(
                    "SELECT has_table_privilege('rushes_app','provider_spend_settlement','SELECT') "
                    "AND has_table_privilege('rushes_app','provider_spend_settlement','INSERT') "
                    "AND NOT has_table_privilege('rushes_app','provider_spend_settlement','UPDATE,DELETE')"
                ).fetchone()[0]
                assert (
                    db.execute(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_name='analysis_window' "
                        "AND column_name IN ('provider_file_expires_at','provider_file_retry_at') "
                        "AND data_type='timestamp with time zone' AND is_nullable='YES'"
                    ).fetchone()[0]
                    == 2
                )
                assert (
                    db.execute(
                        "SELECT count(*) FROM pg_class WHERE relname IN ('google_identity', 'oauth_attempt') "
                        "AND NOT relrowsecurity AND relnamespace = 'public'::regnamespace"
                    ).fetchone()[0]
                    == 2
                )
                assert (
                    db.execute(
                        "SELECT count(*) FROM pg_constraint WHERE contype = 'f' AND confdeltype = 'c' "
                        "AND conrelid IN ('google_identity'::regclass, 'oauth_attempt'::regclass)"
                    ).fetchone()[0]
                    == 2
                )
                assert (
                    db.execute(
                        "SELECT count(*) FROM information_schema.columns WHERE table_name='reservation' AND column_name='cycle'"
                    ).fetchone()[0]
                    == 1
                )
            report = {
                "passed": True,
                "forced_rls_tables": forced,
                "schema_version": version,
                "database": "isolated disposable test database; dropped after verification",
            }
            Path("docs/validation/fresh-migrations.json").write_text(
                json.dumps(report, indent=2) + "\n"
            )
            print(f"Fresh migrations passed: version {version}, {forced} forced-RLS tables.")
        finally:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


if __name__ == "__main__":
    main()
