import asyncio
import fcntl
import hashlib
import os
import shutil
from contextlib import contextmanager, suppress
from functools import wraps
from pathlib import Path
from typing import BinaryIO, TextIO
from uuid import UUID

from rushes.config import settings
from rushes.db import WorkspaceBusyError


class StorageError(ValueError):
    pass


def sync_file(file: BinaryIO | TextIO) -> None:
    file.flush()
    os.fsync(file.fileno())


def authorized_source_root(root: str | Path, workspace_id, asset_id) -> Path:
    from uuid import UUID

    from rushes.config import settings

    config = settings()
    path = Path(root)
    uploaded = (
        config.storage_root / "uploads" / str(UUID(str(workspace_id))) / str(UUID(str(asset_id)))
    )
    if path != uploaded and path not in config.source_roots:
        raise StorageError(
            "Source root is no longer configured. Restore its allowlist entry or relink this asset."
        )
    return path


@contextmanager
def open_source(root: Path, relative: str):
    """Walk beneath a trusted root using directory FDs, rejecting every symlink."""
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(p in {"..", "."} for p in path.parts):
        raise StorageError("Select a file within the configured source root")
    handles = []
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        handles.append(directory)
        for part in path.parts[:-1]:
            directory = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
            )
            handles.append(directory)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        handles.append(fd)
        import stat

        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise StorageError("Only regular source files are supported")
        with os.fdopen(os.dup(fd), "rb") as file:
            yield file
    except OSError as error:
        raise StorageError("Source is missing, inaccessible, or contains a symlink") from error
    finally:
        for handle in reversed(handles):
            os.close(handle)


def fingerprint(file: BinaryIO) -> str:
    file.seek(0)
    digest = hashlib.file_digest(file, "sha256").hexdigest()
    file.seek(0)
    return digest


def require_space(root: Path, expected_bytes: int, minimum_free: int):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    free = shutil.disk_usage(root).free
    required = expected_bytes + minimum_free
    if free < required:

        def size(amount):
            for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
                if amount < 1024 or unit == "TiB":
                    return f"{amount:.2f} {unit}" if unit != "B" else f"{amount} B"
                amount /= 1024

        raise StorageError(
            f"Insufficient server storage: {size(free)} free, "
            f"{size(minimum_free)} kept in reserve, and {size(expected_bytes)} "
            f"needed for this operation. Free another {size(required - free)} "
            "on the server, then try again. Manage files and exports to free space; "
            "check storage in Settings."
        )


def artifact_path(root: Path, workspace_id: str, asset_id: str, name: str) -> Path:
    from uuid import UUID

    if Path(name).name != name or name in {".", ".."}:
        raise StorageError("Invalid artifact name")
    folder = root / str(UUID(workspace_id)) / str(UUID(asset_id))
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    return folder / name


@contextmanager
def workspace_file_lease(workspace_id: UUID, *, exclusive=False):
    """Uploads and activities hold a shared lease without occupying a DB connection."""
    root = settings().storage_root
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root_fd = lock_fd = folder_fd = None
    try:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.mkdir(".workspace-locks", mode=0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        folder_fd = os.open(
            ".workspace-locks", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
        )
        lock_fd = os.open(
            f"{UUID(str(workspace_id))}.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
            mode=0o600,
            dir_fd=folder_fd,
        )
        fcntl.flock(lock_fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        yield
    except BlockingIOError as error:
        raise WorkspaceBusyError(
            "An upload, processing task, or deletion is active in this workspace. Let it finish, then retry."
        ) from error
    finally:
        for fd in (lock_fd, folder_fd, root_fd):
            if fd is not None:
                os.close(fd)


def storage_activity(function):
    """Keep deletion out until an activity's filesystem/provider work has actually stopped."""

    @wraps(function)
    async def guarded(args: dict):
        with workspace_file_lease(UUID(args["workspace_id"])):
            return await function(args)

    return guarded


async def run_storage_thread(function, *args, **kwargs):
    """Cancellation drains the thread before unwinding its surrounding activity/file lease."""
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        with suppress(Exception, asyncio.CancelledError):
            task.result()
        raise
