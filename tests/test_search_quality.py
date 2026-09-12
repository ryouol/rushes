import asyncio
import threading
from types import SimpleNamespace

import pytest
from rushes import remote_compute, routes_search, search_compute
from rushes.local_models import RERANKER_MODEL
from rushes.search_compute import SearchComputations


async def test_search_timeout_reuses_completed_work_without_another_dispatch(monkeypatch):
    monkeypatch.setattr(search_compute, "SEARCH_WAIT_SECONDS", 0.02)
    cache = SearchComputations()
    release = threading.Event()
    calls = []

    def compute():
        calls.append(1)
        release.wait(2)
        return [0.5]

    try:
        with pytest.raises(TimeoutError):
            await cache.get("same-query", compute)
        pending = cache.pending["same-query"]
        release.set()
        assert await pending == [0.5]
        assert await cache.get("same-query", compute) == [0.5]
        assert calls == [1]
        assert not cache.pending
    finally:
        release.set()


async def test_concurrent_identical_searches_share_one_computation():
    cache = SearchComputations()
    calls = []

    def compute():
        calls.append(1)
        return [0.7]

    assert await asyncio.gather(cache.get("query", compute), cache.get("query", compute)) == [
        [0.7],
        [0.7],
    ]
    assert calls == [1]


def test_distinct_moments_do_not_expand_a_precise_match_to_the_whole_video():
    def result(start, end, evidence):
        return {"asset_id": "one", "start_us": start, "end_us": end, "evidence": [evidence]}

    results = routes_search.distinct_moments(
        [
            result(10_000_000, 12_000_000, "specific action"),
            result(0, 60_000_000, "broad shot"),
            result(10_000_000, 12_000_000, "same range"),
            result(40_000_000, 42_000_000, "second action"),
        ],
        20,
    )
    assert [(r["start_us"], r["end_us"]) for r in results] == [
        (10_000_000, 12_000_000),
        (0, 60_000_000),
        (40_000_000, 42_000_000),
    ]
    assert results[0]["evidence"] == ["specific action", "same range"]


@pytest.mark.parametrize(
    "response",
    [
        {"model": "wrong", "scores": [1]},
        {"model": RERANKER_MODEL, "scores": []},
        {"model": RERANKER_MODEL, "scores": [float("nan")]},
    ],
)
def test_remote_relevance_validates_model_count_and_finite_scores(monkeypatch, response):
    monkeypatch.setattr(remote_compute, "reserve_provider_call", lambda _: None)
    monkeypatch.setattr(
        remote_compute,
        "remote_function",
        lambda _: SimpleNamespace(
            spawn=lambda *args, **kwargs: SimpleNamespace(get=lambda **kw: response)
        ),
    )
    with pytest.raises(ValueError):
        remote_compute.RemoteEmbedder().rerank("red car", ["A red car"])


@pytest.mark.integration
async def test_relevance_rejects_unrelated_evidence_and_retains_exact_timestamps(
    authenticated, monkeypatch
):
    from uuid import uuid4

    clients, workspace, _, project, asset, _ = authenticated
    for description, start, end in [
        ("A red notebook opens", 1_000_000, 2_000_000),
        ("A red car drives", 0, 10_000_000),
    ]:
        result = await clients[0].post(
            f"/api/workspaces/{workspace}/assets/{asset}/observations",
            json={
                "description": description,
                "start_us": start,
                "end_us": end,
                "request_id": str(uuid4()),
            },
        )
        assert result.status_code == 201

    async def vector(*args):
        return None, None

    async def relevance(workspace, query, texts):
        return [-0.461 if "notebook" in text else -10 for text in texts]

    monkeypatch.setattr(routes_search, "query_embedding", vector)
    monkeypatch.setattr(routes_search, "relevance_scores", relevance)
    results, notice, _ = await routes_search.retrieve(
        SimpleNamespace(workspace_id=workspace), project, "red"
    )
    assert notice is None and len(results) == 1
    assert (results[0]["start_us"], results[0]["end_us"]) == (1_000_000, 2_000_000)
    assert "notebook" in results[0]["evidence"][0]["description"]


def test_remote_timeout_reuses_call_and_reclaims_completed_capacity(monkeypatch):
    from modal.exception import TimeoutError as PollTimeout

    ready, dispatched = set(), []

    def spawn(texts, **kwargs):
        key = texts[0]
        dispatched.append(key)

        def get(timeout):
            if key not in ready:
                raise PollTimeout()
            return {"model": remote_compute.REMOTE_EMBEDDING_MODEL, "vectors": [[0.01] * 384]}

        return SimpleNamespace(get=get)

    monkeypatch.setattr(remote_compute, "reserve_provider_call", lambda _: None)
    monkeypatch.setattr(remote_compute, "remote_function", lambda _: SimpleNamespace(spawn=spawn))
    model = remote_compute.RemoteEmbedder()
    for i in range(8):
        with pytest.raises(PollTimeout):
            model.embed([str(i)])
    ready.update(str(i) for i in range(9))
    assert model.embed(["8"]) == [[0.01] * 384]
    assert model.embed(["7"]) == [[0.01] * 384]
    assert len(dispatched) == 9 and not model.calls


def test_terminal_remote_failure_releases_capacity(monkeypatch):
    def fail(**kwargs):
        raise ValueError("Synthetic terminal model failure")

    monkeypatch.setattr(remote_compute, "reserve_provider_call", lambda _: None)
    monkeypatch.setattr(
        remote_compute,
        "remote_function",
        lambda _: SimpleNamespace(spawn=lambda *args, **kwargs: SimpleNamespace(get=fail)),
    )
    model = remote_compute.RemoteEmbedder()
    for i in range(9):
        with pytest.raises(ValueError, match="terminal model failure"):
            model.embed([str(i)])
    assert not model.calls
