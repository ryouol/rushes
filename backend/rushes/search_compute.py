"""Bounded, shared search computations that survive an impatient client."""

import asyncio
import hashlib
import json
import time
from collections import OrderedDict

from rushes.config import settings
from rushes.inference import embedder
from rushes.local_models import RERANKER_MODEL

SEARCH_WAIT_SECONDS = 75
CACHE_SECONDS = 600
MAX_CACHED = 128
MAX_PENDING = 8


class SearchComputations:
    def __init__(self):
        self.ready = OrderedDict()
        self.pending = {}
        self.limit = asyncio.Semaphore(1)

    async def get(self, key, compute):
        now = time.monotonic()
        for old in list(self.ready):
            if self.ready[old][0] <= now:
                del self.ready[old]
        if key in self.ready:
            self.ready.move_to_end(key)
            return self.ready[key][1]
        if key not in self.pending:
            if len(self.pending) >= MAX_PENDING:
                raise ValueError("Search is busy. Try again shortly.")

            async def run():
                try:
                    async with self.limit:
                        value = await asyncio.to_thread(compute)
                    self.ready[key] = (time.monotonic() + CACHE_SECONDS, value)
                    while len(self.ready) > MAX_CACHED:
                        self.ready.popitem(last=False)
                    return value
                finally:
                    self.pending.pop(key, None)

            task = asyncio.create_task(run())
            task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
            self.pending[key] = task
        return await asyncio.wait_for(asyncio.shield(self.pending[key]), SEARCH_WAIT_SECONDS)


computations = SearchComputations()


def cache_key(kind, workspace, query, texts=()):
    config = settings()
    return hashlib.sha256(
        json.dumps(
            [
                kind,
                str(workspace),
                config.compute_backend,
                config.modal_environment,
                config.embedding_model,
                RERANKER_MODEL,
                query,
                texts,
            ]
        ).encode()
    ).hexdigest()


async def relevance_scores(workspace, query, texts):
    scores = []
    for start in range(0, len(texts), 32):
        batch = texts[start : start + 32]
        scores.extend(
            await computations.get(
                cache_key("relevance", workspace, query, batch),
                lambda batch=batch: embedder().rerank(query, batch),
            )
        )
    return scores
