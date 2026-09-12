from datetime import UTC, datetime


def provider_file_expired(expires_at: datetime | None) -> bool:
    return (
        expires_at is not None and expires_at.tzinfo is not None and expires_at <= datetime.now(UTC)
    )


def record_provider_file(window, name: str | None, expires_at: datetime | None = None):
    window.provider_file = name
    window.provider_file_expires_at = expires_at if name else None
    window.provider_file_retry_at = None


def delete_provider_file(client, name: str, expires_at: datetime | None = None) -> None:
    from google.genai import errors

    if provider_file_expired(expires_at):
        return
    try:
        client.files.delete(name=name)
    except errors.ClientError as error:
        if error.code != 404:
            raise
