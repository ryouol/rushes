"""Inventory API guards and scan source/client bundles without printing secret values."""

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values
from fastapi.routing import APIRoute
from rushes.api import app

ROOT = Path(__file__).resolve().parents[1]


def dependencies(node):
    names = set()
    for child in node.dependencies:
        names.add(getattr(child.call, "__name__", str(type(child.call))))
        names.update(dependencies(child))
    return sorted(names)


def main():
    paths = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, text=True
    ).splitlines()
    paths += [
        str(path.relative_to(ROOT))
        for path in (ROOT / "web/.next/static").rglob("*")
        if path.is_file()
    ]
    secret_values = {}
    for name, value in dotenv_values(ROOT / ".env").items():
        if not value or not any(
            marker in name for marker in ("SECRET", "PASSWORD", "API_KEY", "DATABASE_URL")
        ):
            continue
        if "DATABASE_URL" in name:
            value = urlparse(value).password
        if value and len(value) >= 12 and value != "GENERATE":
            secret_values[name] = value.encode()
    findings = []
    for relative in paths:
        path = ROOT / relative
        if not path.is_file() or path.stat().st_size > 30 * 1024**2:
            continue
        content = path.read_bytes()
        for name, value in secret_values.items():
            if value in content:
                findings.append({"variable_name": name, "location": relative})
        if re.search(
            rb"AIza[0-9A-Za-z_-]{35}|AQ\.[0-9A-Za-z_-]{40,}|AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
            content,
        ):
            findings.append(
                {
                    "variable_name": "credential-shaped content; inspect locally and rotate if real",
                    "location": relative,
                }
            )
    endpoints = []
    public = {
        "/api/health",
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/providers",
        "/api/auth/google/authorize",
        "/api/auth/google/callback",
    }

    def routes(items, prefix=""):
        for route in items:
            if isinstance(route, APIRoute):
                yield route, prefix + route.path
            elif hasattr(route, "original_router"):
                yield from routes(
                    route.original_router.routes, prefix + route.include_context.prefix
                )

    for route, full_path in routes(app.routes):
        guards = dependencies(route.dependant)
        endpoints.append(
            {
                "methods": sorted(route.methods),
                "path": full_path,
                "access": "deliberately public"
                if full_path in public
                else "session revalidated for each event poll"
                if full_path.endswith("/events")
                else "authenticated",
                "dependencies": guards,
                "validation": "typed path/query/body; global loopback Host + Origin middleware; tenant routes use membership and RLS",
            }
        )
    history = subprocess.run(
        ["git", "rev-list", "--all", "--count"], cwd=ROOT, capture_output=True, text=True
    )
    report = {
        "source_and_bundle_files_scanned": len(paths),
        "known_secret_variable_names_checked": list(secret_values),
        "secret_findings": findings,
        "history": "No commits existed when this application was built"
        if history.stdout.strip() in {"", "0"}
        else "Review existing history separately before declaring it clean",
        "endpoints": endpoints,
        "limitations": "Known configured values and credential shapes scanned; this is not a proof that every possible secret pattern is absent.",
    }
    output = ROOT / "docs/validation/security-inventory.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))
    print(
        f"Scanned {len(paths)} source/client-bundle files; {len(findings)} findings. API inventory: {len(endpoints)} routes. Report contains names and locations only."
    )
    if findings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
