"""Bounded private RPCs; remote compute never receives database access or source paths."""

import math
from pathlib import Path

from rushes.config import settings
from rushes.provider_budget import reserve_provider_call
from rushes.timing import Interval

MODAL_APP = "rushes-compute"
REMOTE_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
REMOTE_TRANSCRIPTION_MODEL = "tiny"
MAX_AUDIO_BYTES = 4 * 1024**2


def remote_function(name: str):
    import modal

    return modal.Function.from_name(MODAL_APP, name, environment_name=settings().modal_environment)


def validate_texts(texts: list[str]) -> None:
    if not 1 <= len(texts) <= 32 or any(len(text.encode("utf-8")) > 16000 for text in texts):
        raise ValueError("Remote embedding requires 1–32 texts of at most 16,000 UTF-8 bytes each")


class RemoteEmbedder:
    model = REMOTE_EMBEDDING_MODEL

    def embed(self, texts: list[str]) -> list[list[float]]:
        validate_texts(texts)
        reserve_provider_call("modal")
        result = remote_function("embed").remote(texts)
        vectors = result["vectors"]
        if result["model"] != self.model or len(vectors) != len(texts):
            raise ValueError(
                "Remote embedding response does not match the configured model or batch"
            )
        if any(
            len(vector) != 384 or not all(math.isfinite(x) for x in vector) for vector in vectors
        ):
            raise ValueError("Remote embedding returned invalid vectors")
        return vectors


def transcribe_remote(chunk: Path, window: Interval) -> list[dict]:
    if window.end_us - window.start_us > 60_000_000:
        raise ValueError("Remote transcription requires windows of at most 60 seconds")
    with chunk.open("rb") as file:
        audio = file.read(MAX_AUDIO_BYTES + 1)
    if not audio or len(audio) > MAX_AUDIO_BYTES:
        raise ValueError("Derived audio exceeds the remote transcription limit")
    reserve_provider_call("modal")
    result = remote_function("transcribe_audio").remote(audio, window.model_dump())
    if result["model"] != REMOTE_TRANSCRIPTION_MODEL or len(result["segments"]) > 1000:
        raise ValueError("Remote transcription response does not match its request")
    for row in result["segments"]:
        interval = Interval(start_us=row["start_us"], end_us=row["end_us"])
        if interval.start_us < window.start_us or interval.end_us > window.end_us:
            raise ValueError("Remote transcript lies outside its source window")
    return result["segments"]
