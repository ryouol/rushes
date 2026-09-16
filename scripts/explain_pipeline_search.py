"""Capture plans for the actual retrieval statements under the runtime tenant role.

Run only on an isolated synthetic project: EXPLAIN ANALYZE executes each SELECT.
"""

import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from rushes.db import session_factory, tenant_session
from rushes.routes_search import retrieve
from sqlalchemy import event


async def run(workspace, project, output):
    captured = []
    engine = session_factory().kw["bind"]

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith("SELECT") and (
            "FROM observation" in statement or "JOIN embedding" in statement
        ):
            captured.append((statement, parameters))

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        await retrieve(SimpleNamespace(workspace_id=workspace), project, "red bicycle")
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)
    plans = []
    async with tenant_session(workspace) as db:
        connection = await db.connection()
        await connection.exec_driver_sql("SET LOCAL hnsw.iterative_scan = 'strict_order'")
        await connection.exec_driver_sql("SET LOCAL hnsw.max_scan_tuples = 10000")
        for statement, parameters in captured:
            result = await connection.exec_driver_sql(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, parameters
            )
            plans.append({"statement": statement, "plan": result.scalar()})
    output.write_text(json.dumps(plans, indent=2) + "\n")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=UUID, required=True)
    parser.add_argument("--project", type=UUID, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.workspace, args.project, args.output))
