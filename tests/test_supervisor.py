import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_invalid_startup_configuration_failure_reaches_supervisor(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/serve.py")],
        cwd=ROOT,
        env={
            **os.environ,
            "RUSHES_ORIGIN": "https://rushes.example.com",
            "RUSHES_CLIENT_IP_HEADER": "",
            "RUSHES_STORAGE_ROOT": str(tmp_path / "storage"),
            "RUSHES_OUTPUT_ROOT": str(tmp_path / "exports"),
        },
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert "startup helper failed" in result.stderr
    assert not (tmp_path / "storage").exists()


def test_shutdown_during_preparation_reaps_the_real_helper_process(tmp_path):
    package = tmp_path / "rushes"
    package.mkdir()
    (package / "__init__.py").write_text("")
    marker = tmp_path / "helper.pid"
    (package / "workflow_service.py").write_text(
        "import os,time\nfrom pathlib import Path\n"
        f"path=Path({str(marker)!r})\n"
        "temporary=path.with_suffix('.tmp')\n"
        "temporary.write_text(str(os.getpid()))\ntemporary.replace(path)\ntime.sleep(60)\n"
    )
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts/serve.py")],
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHONPATH": str(tmp_path),
            "RUSHES_ORIGIN": "http://localhost:3844",
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    helper = None
    try:
        deadline = time.monotonic() + 10
        while not marker.exists():
            assert process.poll() is None
            assert time.monotonic() < deadline, "Preparation helper did not start"
            time.sleep(0.05)
        helper = int(marker.read_text())
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 0, (stdout, stderr)
        with pytest.raises(ProcessLookupError):
            os.kill(helper, 0)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if helper is not None:
            try:
                os.kill(helper, signal.SIGKILL)
            except ProcessLookupError:
                pass
