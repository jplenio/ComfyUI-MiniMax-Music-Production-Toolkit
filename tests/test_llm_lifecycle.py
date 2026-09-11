"""Lifecycle tests for the integrated LLM node (IMPROVE-TODO R02).

Covers the promises this task makes:

* a model switch closes the previous model **before** the new one is allocated,
  so two models are never resident at once and a failed load leaves no stale
  cache entry;
* the cache key carries the checkpoint's file signature;
* session snapshots are keyed by model/context/template identity and bounded;
* the turn (restore, generation, save) holds the model lock, so unload can
  never close a model during native inference;
* the streaming iterator is closed on every path, and a ComfyUI cancel stops
  generation between chunks.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_toolkit_modules():
    pkg_name = "_toolkit_llm_lifecycle_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(ROOT)]
    sys.modules[pkg_name] = pkg
    loaded = {}
    for module_name in (
        "toolkit_logging",
        "comfy_resources",
        "model_downloader",
        "progress_utils",
        "llm_chat",
    ):
        full = f"{pkg_name}.{module_name}"
        spec = importlib.util.spec_from_file_location(full, ROOT / f"{module_name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        loaded[module_name] = module
    return loaded


MODULES = load_toolkit_modules()
llm = MODULES["llm_chat"]
progress = MODULES["progress_utils"]


class FakeBar:
    def update_absolute(self, value):
        pass


class FakeStream:
    """Stream wrapper that records whether it was closed."""

    def __init__(self, chunks, fail_after=None):
        self._chunks = list(chunks)
        self._fail_after = fail_after
        self.closed = False

    def __iter__(self):
        for index, chunk in enumerate(self._chunks):
            if self._fail_after is not None and index >= self._fail_after:
                raise RuntimeError("stream failed")
            yield chunk

    def close(self):
        self.closed = True


class FakeLlama:
    """Minimal stand-in for ``llama_cpp.Llama``."""

    events = []
    fail_for = ()
    stream_chunks = [{"choices": [{"delta": {"content": "part"}}]} for _ in range(3)]

    def __init__(self, model_path=None, verbose=False, **options):
        name = Path(model_path).name
        if name in FakeLlama.fail_for:
            FakeLlama.events.append(("fail", name))
            raise RuntimeError("could not load the model")
        self.model_path = model_path
        self.options = options
        self.closed = False
        self.state = b"initial"
        self.restored_with = None
        self.set_state_called = False
        self.last_stream = None
        FakeLlama.events.append(("construct", name))

    def close(self):
        self.closed = True
        FakeLlama.events.append(("close", Path(self.model_path).name))

    def create_chat_completion(self, messages=None, max_tokens=0, temperature=0.0, top_p=0.0, stream=False, **kwargs):
        if stream:
            self.last_stream = FakeStream(FakeLlama.stream_chunks)
            return self.last_stream
        return {"choices": [{"message": {"content": "hello"}}]}

    def save_state(self):
        return b"snapshot"

    def load_state(self, state):
        self.restored_with = state

    def set_state(self, state):  # pragma: no cover - only used when load_state is absent
        self.set_state_called = True


class FakeLlamaNoLoadState(FakeLlama):
    load_state = None


class LifecycleTestCase(unittest.TestCase):
    def setUp(self):
        FakeLlama.events = []
        FakeLlama.fail_for = ()
        llm._loaded_models.clear()
        llm._sessions.clear()
        llm._loaded_llama_cpp = types.SimpleNamespace(Llama=FakeLlama, __version__="test")
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "model-a.gguf"
        self.path.write_bytes(b"A" * 1024)
        self.other = Path(self._tmp.name) / "model-b.gguf"
        self.other.write_bytes(b"B" * 2048)

    def patch(self, obj, name, value):
        original = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(setattr, obj, name, original)

    def load(self, path):
        self.patch(llm, "_find_model_path", lambda name: Path(path))
        return llm._get_model(str(Path(path).name), auto_download=False)

    def names(self):
        return [Path(key.split("|")[0]).name for key in llm._loaded_models]


class ModelSwitchTests(LifecycleTestCase):
    def test_previous_model_is_closed_before_the_next_is_constructed(self):
        self.patch(llm, "_find_model_path", lambda name: self.path)
        first = llm._get_model("model-a.gguf", auto_download=False)
        self.patch(llm, "_find_model_path", lambda name: self.other)
        second = llm._get_model("model-b.gguf", auto_download=False)
        self.assertIsNot(first, second)
        self.assertTrue(first.closed)
        self.assertEqual(
            [event for event in FakeLlama.events if event[0] in ("construct", "close")],
            [("construct", "model-a.gguf"), ("close", "model-a.gguf"), ("construct", "model-b.gguf")],
        )
        # at most one managed model is resident
        self.assertEqual(len(llm._loaded_models), 1)

    def test_identical_request_is_served_from_the_cache(self):
        self.patch(llm, "_find_model_path", lambda name: self.path)
        first = llm._get_model("model-a.gguf", auto_download=False)
        second = llm._get_model("model-a.gguf", auto_download=False)
        self.assertIs(first, second)
        self.assertEqual([e for e in FakeLlama.events if e[0] == "construct"], [("construct", "model-a.gguf")])

    def test_changed_file_signature_invalidates_the_cache(self):
        self.patch(llm, "_find_model_path", lambda name: self.path)
        llm._get_model("model-a.gguf", auto_download=False)
        self.path.write_bytes(b"A" * 4096)  # size and mtime change
        second = llm._get_model("model-a.gguf", auto_download=False)
        self.assertEqual(len([e for e in FakeLlama.events if e[0] == "construct"]), 2)
        self.assertTrue(second.closed is False)

    def test_failed_load_releases_the_previous_model_and_leaves_no_cache(self):
        self.patch(llm, "_find_model_path", lambda name: self.path)
        first = llm._get_model("model-a.gguf", auto_download=False)
        FakeLlama.fail_for = ("model-b.gguf",)
        self.patch(llm, "_find_model_path", lambda name: self.other)
        with self.assertRaises(RuntimeError) as ctx:
            llm._get_model("model-b.gguf", auto_download=False)
        self.assertTrue(first.closed, "the previous model must not stay resident as a rollback")
        self.assertEqual(llm._loaded_models, {})
        self.assertIn("Underlying error: RuntimeError", str(ctx.exception))
        self.assertNotIn("VRAM was likely exhausted", str(ctx.exception))


class UnloadAndLockTests(LifecycleTestCase):
    def test_unload_node_releases_models_and_sessions(self):
        self.patch(llm, "_find_model_path", lambda name: self.path)
        model = llm._get_model("model-a.gguf", auto_download=False)
        llm._sessions["x"] = b"state"
        # The node is the documented path: it frees the models and then the
        # now-orphaned snapshots explicitly (unload_llm_models itself keeps the
        # snapshot API separate).
        trigger, released = llm.MiniMaxLLMUnload().unload("t", True, False)
        self.assertEqual((trigger, released), ("t", 1))
        self.assertTrue(model.closed)
        self.assertEqual(llm._loaded_models, {})
        self.assertEqual(dict(llm._sessions), {})

    def test_models_and_snapshots_can_be_released_separately(self):
        self.patch(llm, "_find_model_path", lambda name: self.path)
        model = llm._get_model("model-a.gguf", auto_download=False)
        llm._sessions["x"] = b"state"
        self.assertEqual(llm.unload_llm_models(), 1)
        self.assertTrue(model.closed)
        self.assertEqual(llm._loaded_models, {})
        self.assertEqual(dict(llm._sessions), {"x": b"state"})
        llm._clear_llm_sessions()
        self.assertEqual(dict(llm._sessions), {})

    def test_unload_waits_for_a_running_turn(self):
        done = threading.Event()
        llm._MODEL_LOCK.acquire()
        try:
            worker = threading.Thread(target=lambda: (llm.unload_llm_models(), done.set()))
            worker.start()
            self.assertFalse(done.wait(0.3), "unload must not run while the model lock is held")
        finally:
            llm._MODEL_LOCK.release()
        self.assertTrue(done.wait(5))
        worker.join(timeout=5)


class SessionSnapshotTests(LifecycleTestCase):
    def test_session_key_carries_model_context_and_template_identity(self):
        signature = llm._model_signature(self.path)
        key = llm._session_key("s1", "model-a.gguf", 8192, "chatml", signature)
        self.assertIn("s1", key)
        self.assertIn(signature, key)
        self.assertIn("ctx=8192", key)
        self.assertIn("fmt=chatml", key)
        self.assertNotEqual(key, llm._session_key("s1", "model-a.gguf", 32768, "chatml", signature))
        self.assertNotEqual(
            key, llm._session_key("s1", "model-b.gguf", 8192, "chatml", llm._model_signature(self.other))
        )

    def test_snapshot_storage_is_bounded_by_entry_count(self):
        for index in range(llm.SESSION_SNAPSHOT_MAX_ENTRIES + 6):
            llm._remember_session(f"session-{index}", b"x" * 8)
        self.assertLessEqual(len(llm._sessions), llm.SESSION_SNAPSHOT_MAX_ENTRIES)
        # oldest evicted first (LRU order)
        self.assertIn(f"session-{llm.SESSION_SNAPSHOT_MAX_ENTRIES + 5}", llm._sessions)
        self.assertNotIn("session-0", llm._sessions)

    def test_oversized_snapshot_is_not_cached(self):
        original = llm.SESSION_SNAPSHOT_MAX_BYTES
        self.patch(llm, "SESSION_SNAPSHOT_MAX_BYTES", 4)
        try:
            llm._remember_session("big", b"x" * 1024)
        finally:
            llm.SESSION_SNAPSHOT_MAX_BYTES = original
        self.assertNotIn("big", llm._sessions)

    def test_restore_prefers_the_documented_load_state_call(self):
        model = FakeLlama(str(self.path))
        self.assertTrue(llm._restore_state(model, b"state"))
        self.assertEqual(model.restored_with, b"state")
        self.assertFalse(model.set_state_called)

    def test_restore_falls_back_to_set_state_when_load_state_is_absent(self):
        model = FakeLlamaNoLoadState(str(self.path))
        self.assertTrue(llm._restore_state(model, b"state"))
        self.assertTrue(model.set_state_called)

    def test_missing_snapshot_is_stored_as_none(self):
        class NoSaveState(FakeLlama):
            save_state = None

        llm._remember_session("k", llm._save_state(NoSaveState(str(self.path))))
        self.assertNotIn("k", llm._sessions)


class StreamingTests(LifecycleTestCase):
    def setUp(self):
        super().setUp()
        self.patch(progress, "make_progress_bar", lambda total: FakeBar())

    def test_stream_is_closed_after_a_completed_generation(self):
        model = FakeLlama(str(self.path))
        text, thinking, usage = llm._run_chat_streamed(model, {"messages": [], "max_tokens": 10}, 10)
        self.assertIn("part", text)
        self.assertTrue(model.last_stream.closed)

    def test_stream_is_closed_and_generation_stops_on_cancel(self):
        model = FakeLlama(str(self.path))
        self.patch(llm, "_processing_interrupted", lambda: True)
        with self.assertRaises(Exception) as ctx:
            llm._run_chat_streamed(model, {"messages": [], "max_tokens": 10}, 10)
        self.assertIn("cancel", str(ctx.exception).lower())
        self.assertTrue(model.last_stream.closed, "the native stream must be released on cancel")

    def test_failing_stream_is_closed_too(self):
        class FailingLlama(FakeLlama):
            def create_chat_completion(self, messages=None, max_tokens=0, temperature=0.0, top_p=0.0, stream=False, **kwargs):
                chunks = [{"choices": [{"delta": {"content": "x"}}]} for _ in range(3)]
                self.last_stream = FakeStream(chunks, fail_after=1)
                return self.last_stream

        model = FailingLlama(str(self.path))
        with self.assertRaises(RuntimeError):
            llm._run_chat_streamed(model, {"messages": [], "max_tokens": 10}, 10)
        self.assertTrue(model.last_stream.closed)


class ConcurrencyTests(LifecycleTestCase):
    def setUp(self):
        super().setUp()
        self.patch(progress, "make_progress_bar", lambda total: FakeBar())
        self.patch(llm, "log_llm_environment_once", lambda: None)

    def test_two_turns_never_run_concurrently(self):
        state = {"now": 0, "max": 0}
        guard = threading.Lock()

        class SlowLlama(FakeLlama):
            def create_chat_completion(self, **kwargs):
                with guard:
                    state["now"] += 1
                    state["max"] = max(state["max"], state["now"])
                try:
                    time.sleep(0.05)
                    if kwargs.get("stream"):
                        self.last_stream = FakeStream(FakeLlama.stream_chunks)
                        return self.last_stream
                    return {"choices": [{"message": {"content": "ok"}}]}
                finally:
                    with guard:
                        state["now"] -= 1

        llm._loaded_llama_cpp = types.SimpleNamespace(Llama=SlowLlama, __version__="test")
        self.patch(llm, "_find_model_path", lambda name: self.path)
        node = llm.MiniMaxLLMChat()
        results = []
        errors = []

        def turn():
            try:
                results.append(node.chat(True, "hello", "system", "s1", "model-a.gguf"))
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        workers = [threading.Thread(target=turn) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=30)
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(state["max"], 1, "two turns must not overlap in the native model")


if __name__ == "__main__":
    unittest.main()
