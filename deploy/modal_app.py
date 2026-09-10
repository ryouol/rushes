"""Private, on-demand speech and embedding compute for RUSHES."""

import tempfile
from functools import lru_cache
from pathlib import Path

import modal
from rushes.local_models import LocalEmbedder, ModelOptions, transcribe_local, transcription_model
from rushes.remote_compute import (
    MAX_AUDIO_BYTES,
    MODAL_APP,
    REMOTE_EMBEDDING_MODEL,
    REMOTE_TRANSCRIPTION_MODEL,
    validate_texts,
)
from rushes.timing import Interval

OPTIONS = ModelOptions(
    REMOTE_TRANSCRIPTION_MODEL, REMOTE_EMBEDDING_MODEL, 2, Path("/opt/rushes-models")
)
app = modal.App(MODAL_APP)


def cache_models():
    transcription_model(OPTIONS)
    LocalEmbedder(OPTIONS).embed(["Initialize the embedding model cache."])


image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libgomp1")
    .uv_sync(extra_options="--no-dev", uv_version="0.12.8")
    .add_local_python_source("rushes", copy=True)
    .run_function(cache_models, cpu=1, memory=2048, timeout=600)
)


@lru_cache(maxsize=1)
def embedding_model():
    return LocalEmbedder(OPTIONS)


@app.function(
    image=image,
    cpu=(1, 1),
    memory=(2048, 2048),
    min_containers=0,
    max_containers=1,
    scaledown_window=10,
    timeout=120,
    startup_timeout=60,
    retries=0,
)
def embed(texts: list[str]) -> dict:
    validate_texts(texts)
    return {"model": OPTIONS.embedding_model, "vectors": embedding_model().embed(texts)}


@app.function(
    image=image,
    cpu=(1, 1),
    memory=(2048, 2048),
    min_containers=0,
    max_containers=1,
    scaledown_window=10,
    timeout=120,
    startup_timeout=60,
    retries=0,
)
def transcribe_audio(audio: bytes, window: dict) -> dict:
    interval = Interval.model_validate(window)
    if (
        not audio
        or len(audio) > MAX_AUDIO_BYTES
        or interval.end_us - interval.start_us > 60_000_000
    ):
        raise ValueError(
            "Remote transcription requires at most 60 seconds / 4 MiB of derived audio"
        )
    with tempfile.TemporaryDirectory(prefix="rushes-audio-") as directory:
        chunk = Path(directory) / "derived.wav"
        chunk.write_bytes(audio)
        segments = transcribe_local(chunk, interval, OPTIONS)
    return {"model": OPTIONS.transcription_model, "segments": segments}
