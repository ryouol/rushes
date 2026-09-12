import os
import signal
import socket
import subprocess
import sys
import time
from contextlib import ExitStack
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def running_http(tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    log_path = tmp_path / "server.log"
    with log_path.open("w") as log:
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).parent / "fixtures/public_http_server.py"), str(port)],
            env={**os.environ, "RUSHES_UPLOAD_TIMEOUT_SECONDS": "2"}, stdout=log, stderr=log,
        )
        try:
            with httpx.Client(base_url=f"http://localhost:{port}", trust_env=False, timeout=3) as client:
                deadline = time.monotonic() + 10
                while True:
                    assert process.poll() is None, log_path.read_text()
                    try:
                        if client.get("/api/health").status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    assert time.monotonic() < deadline
                    time.sleep(.05)
                yield client, port, log_path
        finally:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def test_partial_headers_and_bodies_close_but_streamed_upload_and_sse_survive(running_http):
    client, port, _ = running_http
    for initial in (b"GET /api/health HTTP/1.1\r\n", f"POST /api/body HTTP/1.1\r\nHost: localhost:{port}\r\nContent-Length: 4\r\n\r\nx".encode()):
        with socket.create_connection(("127.0.0.1", port), timeout=2) as connection:
            connection.sendall(initial)
            assert connection.recv(1024) == b""
    # Reused connections need the same header deadline as new connections.
    with socket.create_connection(("127.0.0.1", port), timeout=2) as connection:
        connection.sendall(f"GET /api/health HTTP/1.1\r\nHost: localhost:{port}\r\n\r\n".encode())
        response = b""
        while b'{"ok":true}' not in response:
            chunk = connection.recv(1024)
            assert chunk, "Server closed before completing its health response"
            response += chunk
        connection.sendall(b"GET /api/health HTTP/1.1\r\n")
        assert connection.recv(1024) == b""

    def upload():
        yield b"first"
        time.sleep(.6)
        yield b"second"
    response = client.post("/api/workspaces/test/projects/test/upload", content=upload())
    assert response.json() == {"received": 11}
    with client.stream("GET", "/api/events") as response:
        pieces = response.iter_bytes()
        assert next(pieces) == b"data: first\n\n"
        assert next(pieces) == b"data: second\n\n"
    assert client.get("/api/health").status_code == 200


def test_callback_parameters_reach_app_without_access_log_leak(running_http):
    client, _, log_path = running_http
    assert client.get("/api/auth/google/callback?code=synthetic-secret").json() == {"received": True}
    assert "synthetic-secret" not in log_path.read_text()


def test_overload_response_also_redacts_callback_parameters(running_http):
    client, port, log_path = running_http
    with ExitStack() as stack:
        for _ in range(3):
            stack.enter_context(socket.create_connection(("127.0.0.1", port), timeout=2))
        assert client.get("/api/auth/google/callback?code=synthetic-overload-secret").status_code == 503
    assert "synthetic-overload-secret" not in log_path.read_text()


def test_early_response_releases_body_deadline_before_next_request(running_http):
    _, port, _ = running_http
    with socket.create_connection(("127.0.0.1", port), timeout=2) as connection:
        connection.sendall(f"POST /api/reject HTTP/1.1\r\nHost: localhost:{port}\r\nContent-Length: 4\r\n\r\nx".encode())
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = connection.recv(1024)
            assert chunk
            response += chunk
        assert b"403 Forbidden" in response
        time.sleep(.1)
        connection.sendall(b"abcGET /api/health HTTP/1.1\r\n")
        time.sleep(.4)  # Past the old body deadline, within the new header deadline.
        connection.sendall(f"Host: localhost:{port}\r\n\r\n".encode())
        assert b"200 OK" in connection.recv(1024)
