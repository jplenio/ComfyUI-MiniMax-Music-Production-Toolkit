"""Targeted diagnostics tests (F22 / T28)."""
from __future__ import annotations

import importlib
import logging
import os
import re
import sys
import types
import unittest
from pathlib import Path

import _toolkit_bootstrap

ROOT = Path(__file__).resolve().parents[1]
_PACKAGE, _HOST = _toolkit_bootstrap.load_entry_point()
llm_chat = importlib.import_module(f"{_PACKAGE.__name__}.llm_chat")


def _load_logging_module(env_value: str | None):
    """Import toolkit_logging in isolation with a given env value."""
    saved = os.environ.get("MINIMAX_MUSIC_TOOLKIT_LOG_LEVEL")
    if env_value is None:
        os.environ.pop("MINIMAX_MUSIC_TOOLKIT_LOG_LEVEL", None)
    else:
        os.environ["MINIMAX_MUSIC_TOOLKIT_LOG_LEVEL"] = env_value
    name = f"_logging_test_{abs(hash((env_value, id(object()))))}"
    package = types.ModuleType(name)
    package.__path__ = [str(ROOT)]
    sys.modules[name] = package
    try:
        spec = importlib.util.spec_from_file_location(f"{name}.toolkit_logging", ROOT / "toolkit_logging.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"{name}.toolkit_logging"] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
    finally:
        if saved is None:
            os.environ.pop("MINIMAX_MUSIC_TOOLKIT_LOG_LEVEL", None)
        else:
            os.environ["MINIMAX_MUSIC_TOOLKIT_LOG_LEVEL"] = saved
    return module


class LoggingLevelTests(unittest.TestCase):
    def test_default_level(self):
        module = _load_logging_module(None)
        self.assertEqual(module.get_logger().level, logging.INFO)

    def test_named_levels_are_accepted(self):
        for value, expected in (("DEBUG", logging.DEBUG), ("warning", logging.WARNING), ("ERROR", logging.ERROR)):
            with self.subTest(value=value):
                module = _load_logging_module(value)
                self.assertEqual(module.get_logger().level, expected)

    def test_numeric_levels_are_accepted(self):
        module = _load_logging_module("10")
        self.assertEqual(module.get_logger().level, 10)

    def test_non_level_logging_attributes_do_not_break_the_import(self):
        # getattr(logging, "BASIC_FORMAT") is a string; passing it to setLevel
        # used to raise at import time and killed the whole package import.
        module = _load_logging_module("BASIC_FORMAT")
        self.assertEqual(module.get_logger().level, logging.INFO)

    def test_unknown_and_out_of_range_values_fall_back_to_info(self):
        for value in ("NOPE", "9999", "-3"):
            with self.subTest(value=value):
                module = _load_logging_module(value)
                self.assertEqual(module.get_logger().level, logging.INFO)

    def test_blank_value_falls_back(self):
        module = _load_logging_module("   ")
        self.assertEqual(module.get_logger().level, logging.INFO)


class LogTimestampTests(unittest.TestCase):
    """Every toolkit line must say when it happened, so a log reads as a timeline."""

    STAMP = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} ")

    @staticmethod
    def _messages(module, *loggers):
        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        handler = Capture()
        base = module.get_logger()
        base.addHandler(handler)
        previous = base.propagate
        base.propagate = False
        try:
            for logger in loggers:
                logger.info("line from %s", logger.name)
        finally:
            base.removeHandler(handler)
            base.propagate = previous
        return records

    def test_base_child_and_grandchild_lines_are_stamped(self):
        module = _load_logging_module(None)
        loggers = [module.get_logger(), module.get_logger("cover_lyrics"),
                   module.get_logger("cover_lyrics.deep")]
        messages = self._messages(module, *loggers)
        self.assertEqual(len(messages), 3)
        for message, logger in zip(messages, loggers):
            self.assertTrue(self.STAMP.match(message), f"{logger.name}: {message!r}")
            self.assertIn(logger.name, message)

    def test_the_stamp_keeps_lazy_format_arguments_working(self):
        module = _load_logging_module(None)
        messages = self._messages(module, module.get_logger("music_cover"))
        self.assertTrue(self.STAMP.match(messages[0]), messages[0])
        self.assertTrue(messages[0].endswith("line from minimax_music_toolkit.music_cover"),
                        messages[0])

    def test_looking_a_logger_up_again_does_not_stack_the_filter(self):
        """Two filters would print the date twice on every line."""
        module = _load_logging_module(None)
        logger = module.get_logger("music_generation")
        before = len(logger.filters)
        self.assertIs(module.get_logger("music_generation"), logger)
        self.assertEqual(len(logger.filters), before)
        messages = self._messages(module, logger)
        self.assertEqual(len(self.STAMP.findall(messages[0])), 1, messages[0])


class LlmDiagnosticsSourceTests(unittest.TestCase):
    """Source-level guards for the two message fixes (no model required)."""

    def setUp(self):
        self.source = Path(llm_chat.__file__).read_text(encoding="utf-8")

    def test_load_failure_message_interpolates_the_exception(self):
        # The defect was a *literal* placeholder: the fragment lacked the f
        # prefix, so users saw the raw braces instead of the real error.  A plain
        # source substring cannot tell the two apart (a correct f-string contains
        # the same characters), so the module is parsed and every placeholder
        # outside an f-string is reported.
        import ast

        class PlaceholderChecker(ast.NodeVisitor):
            def __init__(self):
                self.bare = []
                self._in_fstring = 0

            def visit_JoinedStr(self, node):
                self._in_fstring += 1
                self.generic_visit(node)
                self._in_fstring -= 1

            def visit_Constant(self, node):
                if self._in_fstring:
                    return
                text = node.value if isinstance(node.value, str) else ""
                if "{exc}" in text or "{type(exc)" in text:
                    self.bare.append(text)

        checker = PlaceholderChecker()
        checker.visit(ast.parse(self.source))
        self.assertEqual(checker.bare, [], "placeholder braces must live inside an f-string")
        self.assertIn('f"{type(exc).__name__}: {exc}"', self.source)

    def test_stream_completion_reports_chunks_not_tokens(self):
        self.assertNotIn("LLM streaming finished: %d tokens.", self.source)
        self.assertIn("stream chunk(s)", self.source)

    def test_failed_model_close_is_reported(self):
        silent = '        except Exception:\n            pass\n        LOGGER.info("Unloaded LLM model'
        self.assertNotIn(silent, self.source, "a failed close must not be silent")
        self.assertIn("Could not close LLM model", self.source)


class UnloadLoggingTests(unittest.TestCase):
    def test_failed_close_is_logged_but_does_not_raise(self):
        saved = dict(llm_chat._loaded_models)

        class BadModel:
            def close(self):
                raise RuntimeError("already torn down")

        llm_chat._loaded_models.clear()
        llm_chat._loaded_models["/models/broken.gguf"] = BadModel()
        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        handler = Capture()
        llm_chat.LOGGER.addHandler(handler)
        try:
            released = llm_chat.unload_llm_models()
        finally:
            llm_chat.LOGGER.removeHandler(handler)
            llm_chat._loaded_models.clear()
            llm_chat._loaded_models.update(saved)

        self.assertEqual(released, 1)
        self.assertTrue(
            any("Could not close LLM model" in record.getMessage() for record in records),
            "the failure must be visible in the log",
        )
        self.assertTrue(any(record.levelno >= logging.WARNING for record in records))


if __name__ == "__main__":
    unittest.main()
