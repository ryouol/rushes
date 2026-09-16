import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from rushes import local_models
from rushes.timing import Interval


def test_shared_whisper_generator_is_consumed_before_next_call(monkeypatch):
    class Model:
        busy = False

        def transcribe(self, *args, **kwargs):
            assert not self.busy, "A second call entered the shared model before consumption"
            self.busy = True

            def segments():
                time.sleep(0.02)
                yield SimpleNamespace(start=0, end=1, text="Synthetic speech", words=[])
                self.busy = False

            return segments(), SimpleNamespace(language="en")

    model = Model()
    monkeypatch.setattr(local_models, "transcription_model", lambda options: model)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: local_models.transcribe_local(
                    "unused", Interval(start_us=0, end_us=2000000), None
                ),
                range(4),
            )
        )
    assert all(result[0]["end_us"] == 1000000 for result in results)
