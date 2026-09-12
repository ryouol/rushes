"""Bounded private RPCs; remote compute never receives database access or source paths."""

import hashlib
import json
import math
import threading
import time
from collections import OrderedDict
from pathlib import Path

from rushes.config import settings
from rushes.local_models import RERANKER_MODEL
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


def validate_query(query: str) -> None:
    if not query.strip() or len(query) > 500:
        raise ValueError("Search queries must contain 1–500 characters")


class RemoteEmbedder:
    model = REMOTE_EMBEDDING_MODEL

    def __init__(self):
        self.calls = {}
        self.completed = OrderedDict()
        self.lock = threading.Lock()

    def finish(self, key, call, result):
        with self.lock:
            if self.calls.get(key) is call:
                self.calls.pop(key)
                self.completed[key] = (time.monotonic() + 600, result)
                while len(self.completed) > 8:
                    self.completed.popitem(last=False)

    def poll(self, key, call, timeout):
        from grpclib import GRPCError
        from modal.exception import ConnectionError as ModalConnectionError
        from modal.exception import FunctionTimeoutError, OutputExpiredError
        from modal.exception import TimeoutError as PollTimeout

        try:
            result = call.get(timeout=timeout)
        except (FunctionTimeoutError, OutputExpiredError):
            with self.lock:
                if self.calls.get(key) is call:
                    self.calls.pop(key)
            raise
        except (PollTimeout, ModalConnectionError, GRPCError, OSError):
            raise  # The remote outcome is uncertain; preserve its handle.
        except Exception:
            with self.lock:
                if self.calls.get(key) is call:
                    self.calls.pop(key)
            raise
        self.finish(key, call, result)
        return result

    def call(self, texts, query=None):
        key = hashlib.sha256(json.dumps([texts, query]).encode()).hexdigest()
        with self.lock:
            retained = list(self.calls.items()) if len(self.calls) >= 8 else []
        for old_key, old_call in retained:
            try:
                self.poll(old_key, old_call, timeout=0)
            except Exception:
                pass
        with self.lock:
            for old_key in list(self.completed):
                if self.completed[old_key][0] <= time.monotonic():
                    del self.completed[old_key]
            if key in self.completed:
                return self.completed[key][1]
            if key not in self.calls:
                if len(self.calls) >= 8:
                    raise ValueError("Search compute is busy; try an existing query shortly")
                reserve_provider_call("modal")
                self.calls[key] = remote_function("embed").spawn(texts, query=query)
            call = self.calls[key]
        # Keep an uncertain call's handle: a later request polls it without paying to dispatch again.
        return self.poll(key, call, timeout=65)

    def embed(self, texts: list[str]) -> list[list[float]]:
        validate_texts(texts)
        result = self.call(texts)
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

    def rerank(self, query: str, texts: list[str]) -> list[float]:
        validate_texts(texts)
        validate_query(query)
        result = self.call(texts, query)
        scores = result["scores"]
        if (
            result["model"] != RERANKER_MODEL
            or len(scores) != len(texts)
            or not all(math.isfinite(score) for score in scores)
        ):
            raise ValueError("Remote relevance scores do not match the requested passages")
        return scores


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
