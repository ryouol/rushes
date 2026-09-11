from types import SimpleNamespace

import pytest
from rushes.storage import StorageError, fingerprint, open_source, require_space


def test_preserves_source_and_hashes(tmp_path):
    source = tmp_path / "camera.mov"
    source.write_bytes(b"original bytes")
    before = source.stat()
    with open_source(tmp_path, source.name) as file:
        assert fingerprint(file) == fingerprint(file)
    assert source.read_bytes() == b"original bytes"
    assert source.stat().st_mtime_ns == before.st_mtime_ns


@pytest.mark.parametrize("relative", ["../secret", "/etc/passwd", "foo/../../secret"])
def test_rejects_traversal(tmp_path, relative):
    with pytest.raises(StorageError), open_source(tmp_path, relative):
        pass


def test_rejects_symlink_in_any_component(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    (actual / "video").write_bytes(b"source")
    (tmp_path / "link").symlink_to(actual, target_is_directory=True)
    (tmp_path / "file").symlink_to(actual / "video")
    for path in ["link/video", "file"]:
        with pytest.raises(StorageError), open_source(tmp_path, path):
            pass


@pytest.mark.parametrize("free", [3 * 1024**3, 4 * 1024**3])
def test_space_check_preserves_reserve_at_and_above_boundary(tmp_path, monkeypatch, free):
    monkeypatch.setattr("rushes.storage.shutil.disk_usage", lambda _: SimpleNamespace(free=free))
    require_space(tmp_path, expected_bytes=1024**3, minimum_free=2 * 1024**3)


@pytest.mark.parametrize(
    ("free", "expected", "reserve", "available", "requested", "additional"),
    [
        (1536 * 1024**2, 1024**3, 2 * 1024**3, "1.50 GiB", "1.00 GiB", "1.50 GiB"),
        (1536 * 1024**2, 0, 2 * 1024**3, "1.50 GiB", "0 B", "512.00 MiB"),
        (1023, 1024, 0, "1023 B", "1.00 KiB", "1 B"),
    ],
)
def test_space_error_explains_shortfall(
    tmp_path, monkeypatch, free, expected, reserve, available, requested, additional
):
    monkeypatch.setattr("rushes.storage.shutil.disk_usage", lambda _: SimpleNamespace(free=free))
    with pytest.raises(StorageError) as failure:
        require_space(tmp_path, expected, reserve)
    message = str(failure.value)
    assert f"{available} free" in message
    assert f"{requested} needed for this operation" in message
    assert f"Free another {additional} on the server" in message
    assert "kept in reserve" in message
