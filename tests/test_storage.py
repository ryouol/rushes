import pytest
from rushes.storage import StorageError, fingerprint, open_source


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
