import json
import os
import signal
import socket
import subprocess
import sys
import time

import httpx
import pytest
from rushes.config import settings
from rushes.http_server import verify_public_config


def test_public_build_config_requires_exact_match(tmp_path):
    expected = settings().public_web_config
    assert not ({"secret", "database_url", "gemini_api_key"} & expected.keys())
    with pytest.raises(RuntimeError, match="Build the web"):
        verify_public_config(tmp_path, expected)
    (tmp_path / "build-config.json").write_text(json.dumps(expected))
    verify_public_config(tmp_path, expected)
    with pytest.raises(RuntimeError, match="configuration changed"):
        verify_public_config(tmp_path, {**expected, "origin": "https://changed.example"})


def test_public_entry_point_uses_environment_port_and_configured_build(tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    origin = f"http://localhost:{port}"
    public = {**settings().public_web_config, "origin": origin, "legal_entity": "Synthetic QA"}
    (tmp_path / "build-config.json").write_text(json.dumps(public))
    (tmp_path / "index.html").write_text("Synthetic static build")
    with (tmp_path / "server.log").open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "rushes.http_server", "--static-root", str(tmp_path)],
            env={
                **os.environ, "PORT": str(port), "RUSHES_BIND_HOST": "127.0.0.1",
                "RUSHES_HOST_WORKFLOW_SERVICE": "false", "RUSHES_GEMINI_API_KEY": "",
                "RUSHES_PROVIDER_MONTHLY_ALLOWANCE_MICROUSD": "0",
                **{"RUSHES_" + key.upper(): value for key, value in public.items()},
            },
            stdout=log, stderr=log,
        )
        try:
            with httpx.Client(base_url=origin, timeout=2, trust_env=False) as client:
                deadline = time.monotonic() + 10
                while True:
                    assert process.poll() is None, (tmp_path / "server.log").read_text()
                    try:
                        response = client.get("/")
                        break
                    except httpx.ConnectError:
                        assert time.monotonic() < deadline
                        time.sleep(.05)
                assert response.status_code == 200 and response.text == "Synthetic static build"
                assert client.get("/api/health").status_code == 200
        finally:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
