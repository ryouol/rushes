from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from threading import Lock

from rushes.telemetry import traced
from rushes.timing import Interval, to_us

RERANKER_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"


@lru_cache(maxsize=1)
def relevance_model(options: "ModelOptions"):
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    return TextCrossEncoder(
        RERANKER_MODEL, threads=options.threads, cache_dir=str(options.cache_root / "reranker")
    )


@dataclass(frozen=True)
class ModelOptions:
    transcription_model: str
    embedding_model: str
    threads: int
    cache_root: Path


@lru_cache(maxsize=1)
def transcription_model(options: ModelOptions):
    from faster_whisper import WhisperModel

    return WhisperModel(
        options.transcription_model,
        device="cpu",
        compute_type="int8",
        cpu_threads=options.threads,
        num_workers=1,
        download_root=str(options.cache_root / "whisper"),
    )


_transcription_lock = Lock()


def transcribe_local(chunk: Path, window: Interval, options: ModelOptions) -> list[dict]:
    # A process shares one WhisperModel. Consume its generator under the same lock
    # as language detection/encoding so concurrent activities cannot interleave calls.
    with _transcription_lock:
        return _transcribe_local(chunk, window, options)


def _transcribe_local(chunk: Path, window: Interval, options: ModelOptions) -> list[dict]:
    segments, info = transcription_model(options).transcribe(
        str(chunk), beam_size=3, vad_filter=True, word_timestamps=True
    )
    rows = []
    for segment in segments:
        start = max(window.start_us, window.start_us + to_us(str(segment.start)))
        end = min(window.end_us, window.start_us + to_us(str(segment.end)))
        if end > start and segment.text.strip():
            rows.append(
                {
                    "start_us": start,
                    "end_us": end,
                    "text": segment.text.strip(),
                    "language": info.language,
                    "words": [asdict(word) for word in (segment.words or [])],
                }
            )
    return rows


class LocalEmbedder:
    def __init__(self, options: ModelOptions):
        from fastembed import TextEmbedding

        self.model = options.embedding_model
        self.options = options
        self.backend = TextEmbedding(
            model_name=self.model,
            threads=options.threads,
            cache_dir=str(options.cache_root / "embedding"),
        )

    @traced("provider.embedding")
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self.backend.embed(texts, batch_size=16)]

    @traced("provider.rerank")
    def rerank(self, query: str, texts: list[str]) -> list[float]:
        return list(relevance_model(self.options).rerank(query, texts, batch_size=4))
