"""Provider contracts, real loopback HTTP, credential isolation and cover bypass."""
import importlib
import asyncio
import json
import math
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from _toolkit_bootstrap import load_entry_point


def setUpModule():
    global providers, chat, artwork, package, handlers
    package, host = load_entry_point()
    handlers = {(method, path): handler for method, path, handler in host.routes}
    providers = importlib.import_module(package.__name__ + ".llm_providers")
    chat = importlib.import_module(package.__name__ + ".llm_chat")
    artwork = importlib.import_module(package.__name__ + ".minimax_artwork")


ANSWER = {"choices": [{"finish_reason": "stop", "message": {"content": "[Title]\nSong"}}]}


class ProviderTests(unittest.TestCase):
    def test_remote_validation_does_not_require_a_saved_gguf(self):
        self.assertIs(chat.MiniMaxLLMChat.VALIDATE_INPUTS(model="missing.gguf", backend=providers.MODES[1]), True)
        self.assertIs(chat.MiniMaxLLMChat.VALIDATE_INPUTS(model="missing.gguf", enabled=False), True)
        self.assertIsInstance(chat.MiniMaxLLMChat.VALIDATE_INPUTS(model="missing.gguf"), str)
        self.assertIsInstance(chat.MiniMaxLLMChat.VALIDATE_INPUTS(enabled="false"), str)

    def test_fresh_execution_needs_no_session_input(self):
        schema = chat.MiniMaxLLMChat.INPUT_TYPES()
        self.assertNotIn("session_id", schema["required"])
        self.assertNotIn("session_id", schema.get("optional", {}))
        first = chat.MiniMaxLLMChat.IS_CHANGED(enabled=True)
        second = chat.MiniMaxLLMChat.IS_CHANGED(enabled=True)
        self.assertTrue(math.isnan(first))
        self.assertNotEqual(first, second)
        self.assertEqual(chat.MiniMaxLLMChat.IS_CHANGED(enabled=False), "disabled")
        with patch.object(chat, "remote_chat", return_value=("Song", "ok", "")) as remote:
            for _ in range(2):
                chat.MiniMaxLLMChat().chat(enabled=True, user_text="Idea", system_prompt="System", backend=providers.MODES[1], remote_model="loaded")
            self.assertEqual(remote.call_count, 2)

    def test_every_provider_preserves_prompt_roles_and_uses_expected_protocol(self):
        responses = {
            "chat": ANSWER,
            "responses": {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "Song"}]}]},
            "anthropic": {"stop_reason": "end_turn", "content": [{"type": "text", "text": "Song"}]},
        }
        for mode, catalog in [(providers.MODES[1], providers.LOCAL), (providers.MODES[2], providers.CLOUD)]:
            for name, (base, protocol, _) in catalog.items():
                with self.subTest(mode=mode, provider=name), patch.object(providers, "credential", return_value="test-key"), patch.object(providers, "request_json", return_value=responses[protocol]) as request:
                    providers.remote_chat(backend=mode, local_provider=name, cloud_provider=name,
                                          server_url=base or "https://example.test/v1", remote_model="test-model",
                                          user_text="USER", system_prompt="SYSTEM", remote_max_tokens=123)
                    url, key, wire, payload, timeout = request.call_args.args
                    self.assertEqual(key, "test-key")
                    self.assertEqual(wire, protocol)
                    self.assertEqual(payload["model"], "test-model")
                    self.assertNotIn("temperature", payload)  # reasoning models may reject it
                    self.assertNotIn("seed", payload)
                    self.assertNotIn("tools", payload)
                    if protocol == "responses":
                        self.assertTrue(url.endswith("/responses"))
                        self.assertEqual(payload["instructions"], "SYSTEM")
                        self.assertEqual(payload["input"], "USER")
                        self.assertFalse(payload["store"])
                        self.assertEqual(payload["max_output_tokens"], 123)
                    else:
                        self.assertEqual(payload["max_tokens"], 123)
                        self.assertEqual(payload["messages"][-1], {"role": "user", "content": "USER"})
                        if protocol == "anthropic":
                            self.assertEqual(payload["system"], "SYSTEM")
                            self.assertEqual(len(payload["messages"]), 1)
                        else:
                            self.assertEqual(payload["messages"][0], {"role": "system", "content": "SYSTEM"})

    def test_external_execution_does_not_import_or_load_gguf(self):
        with patch.object(chat, "_import_llama_cpp", side_effect=AssertionError("Must not load")), patch.object(chat, "remote_chat", return_value=("<think>thought</think>[Title]\nSong", "LLM ok", "")):
            result = chat.MiniMaxLLMChat().chat(True, "Idea", "System", "session", chat.PLACEHOLDER_MODEL, backend=providers.MODES[1], remote_model="loaded")
        self.assertEqual(result, ("[Title]\nSong", "LLM ok", "thought"))

    def test_disabled_llm_never_calls_external_server(self):
        with patch.object(chat, "remote_chat", side_effect=AssertionError("No network")):
            result = chat.MiniMaxLLMChat().chat(False, "", "", "", "", backend=providers.MODES[2])
        self.assertEqual(result[0], "")

    def test_no_request_for_missing_model_or_credential(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(providers, "request_json") as request:
            for model in ("", "model"):
                with self.assertRaises(ValueError):
                    providers.remote_chat(backend=providers.MODES[2], user_text="x", system_prompt="", remote_model=model)
            request.assert_not_called()

    def test_malformed_model_list_has_actionable_error(self):
        with patch.object(providers, "request_json", return_value={"data": None}), self.assertRaisesRegex(ValueError, "manually"):
            providers.list_remote_models(backend=providers.MODES[1])

    def test_reasoning_is_separate_for_all_protocols(self):
        cases = [
            ("chat", {"choices": [{"finish_reason": "stop", "message": {"content": "Final", "reasoning_content": "Thought"}}]}),
            ("anthropic", {"stop_reason": "end_turn", "content": [{"type": "thinking", "thinking": "Thought"}, {"type": "text", "text": "Final"}]}),
            ("responses", {"status": "completed", "output": [{"type": "reasoning", "summary": [{"type": "summary_text", "text": "Thought"}]}, {"type": "message", "content": [{"type": "output_text", "text": "Final"}]}]}),
        ]
        for protocol, response in cases:
            self.assertEqual(providers.parse_response(response, protocol)[:2], ("Final", "Thought"))

    def test_rejects_truncated_refused_empty_and_tool_answers(self):
        cases = [
            ("chat", {"choices": [{"finish_reason": "length", "message": {"content": "Partial"}}]}),
            ("chat", {"choices": [{"finish_reason": "stop", "message": {"content": "", "refusal": "No"}}]}),
            ("chat", {"choices": [{"finish_reason": "tool_calls", "message": {"content": "Partial"}}]}),
            ("chat", {}),
            ("anthropic", {"stop_reason": "max_tokens", "content": [{"type": "text", "text": "Partial"}]}),
            ("responses", {"status": "incomplete", "output": []}),
            ("responses", {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "No"}]}]}),
        ]
        for protocol, response in cases:
            with self.subTest(protocol=protocol, response=response), self.assertRaises((ValueError, RuntimeError)):
                providers.parse_response(response, protocol)

    def test_key_is_bound_to_exact_server_and_can_be_cleared(self):
        handle = providers.remember_key("http://localhost:1234/v1", "test-secret")
        self.assertNotIn("test-secret", handle)
        self.assertEqual(providers.credential("http://localhost:1234/v1", "", credential_id=handle), "test-secret")
        with self.assertRaises(ValueError):
            providers.credential("https://example.test/v1", "", credential_id=handle)
        providers.forget_key(handle)
        with self.assertRaises(ValueError):
            providers.credential("http://localhost:1234/v1", "", credential_id=handle)

    def test_malformed_environment_key_is_not_exposed(self):
        with patch.dict(os.environ, {"TEST_LLM_KEY": "test-secret\nInjected: value"}), self.assertRaises(ValueError) as error:
            providers.credential("http://localhost/v1", "TEST_LLM_KEY")
        self.assertNotIn("test-secret", str(error.exception))

    def test_overridden_host_does_not_inherit_provider_environment_secret(self):
        self.assertEqual(providers.connection(providers.MODES[2])[-1], "OPENAI_API_KEY")
        self.assertEqual(providers.connection(providers.MODES[2], server_url="https://example.test/v1")[-1], "")

    def test_rejects_bad_urls_and_plaintext_cloud(self):
        for url in ("file:///tmp/x", "https://user:secret@example.test/v1", "https://example.test/v1?key=secret", "https://{WorkspaceId}.test/v1", "http://example.test/v1", "https://example.test:bad/v1"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                providers.connection(providers.MODES[2], server_url=url)


class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seen = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.reply()

            def do_POST(self):
                self.reply()

            def reply(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                cls.seen.append((self.path, dict(self.headers), json.loads(body) if body else None))
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "/leaked")
                    self.end_headers()
                    return
                self.send_response(401 if self.path == "/denied" else 200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                data = {"error": "secret-provider-body"} if self.path == "/denied" else ({"data": [{"id": "loaded-model"}]} if self.path.endswith("/models") else ANSWER)
                self.wfile.write(json.dumps(data).encode())
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def test_real_local_server_generation_and_model_discovery(self):
        result = providers.remote_chat(backend=providers.MODES[1], server_url=self.base + "/v1", remote_model="loaded-model", user_text="Song idea", system_prompt="Format")
        self.assertEqual(result[0], "[Title]\nSong")
        self.assertEqual(self.seen[-1][0], "/v1/chat/completions")
        self.assertEqual(providers.list_remote_models(backend=providers.MODES[1], server_url=self.base + "/v1"), ["loaded-model"])

    def test_native_auth_headers(self):
        providers.request_json(self.base + "/v1/messages", "test-secret", "anthropic", {"model": "test"})
        headers = {k.lower(): v for k, v in self.seen[-1][1].items()}
        self.assertEqual(headers["x-api-key"], "test-secret")
        self.assertEqual(headers["anthropic-version"], "2023-06-01")
        self.assertNotIn("authorization", headers)
        providers.request_json(self.base + "/v1/responses", "test-secret", "responses", {})
        headers = {k.lower(): v for k, v in self.seen[-1][1].items()}
        self.assertEqual(headers["authorization"], "Bearer test-secret")

    def test_no_redirect_or_automatic_retry_or_secret_error_body(self):
        for path in ("/redirect", "/denied"):
            start = len(self.seen)
            with self.assertRaises(RuntimeError) as failure:
                providers.request_json(self.base + path, "test-secret", "chat", {})
            self.assertEqual(len(self.seen), start + 1)
            self.assertNotIn("secret", str(failure.exception))
        self.assertFalse(any(item[0] == "/leaked" for item in self.seen))

    def test_response_size_limit(self):
        with patch.object(providers, "MAX_RESPONSE_BYTES", 8), self.assertRaisesRegex(ValueError, "too large"):
            providers.request_json(self.base + "/v1/models", "", "chat")

    def test_timeout_does_not_retry(self):
        with patch.object(providers, "build_opener") as opener:
            opener.return_value.open.side_effect = TimeoutError("do not expose internals")
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                providers.request_json(self.base, "test-secret", "chat", {})
            self.assertEqual(opener.return_value.open.call_count, 1)


class ConfigurationRoutesTests(unittest.TestCase):
    def call(self, body, origin="http://localhost:8188", content_type="application/json"):
        class Request:
            host = "localhost:8188"
            headers = {"Origin": origin}
            async def json(self):
                return body
        request = Request()
        request.content_type = content_type
        return asyncio.run(handlers[("POST", "/minimax_music_toolkit/llm/configure")](request))

    def test_key_entry_returns_only_handle_and_clear_revokes_it(self):
        response = self.call({"action": "set_key", "backend": providers.MODES[1], "local_provider": "LM Studio", "key": "test-secret"})
        self.assertEqual(response.status, 200)
        self.assertNotIn("test-secret", json.dumps(response.payload))
        handle = response.payload["credential_id"]
        self.assertEqual(self.call({"action": "clear_key", "credential_id": handle}).status, 200)
        with self.assertRaises(ValueError):
            providers.credential("http://127.0.0.1:1234/v1", "", credential_id=handle)

    def test_rejects_cross_origin_non_json_and_bad_body(self):
        self.assertEqual(self.call({}, origin="https://other.example").status, 403)
        self.assertEqual(self.call({}, content_type="text/plain").status, 415)
        self.assertEqual(self.call([]).status, 400)
        self.assertEqual(self.call({"action": "invalid"}).status, 400)

    def test_models_route_uses_worker_and_returns_errors_without_tracebacks(self):
        with patch.object(providers, "request_json", return_value={"data": [{"id": "loaded"}]}):
            response = self.call({"action": "models", "backend": providers.MODES[1], "local_provider": "LM Studio"})
            self.assertEqual(response.payload, {"models": ["loaded"]})
        with patch.object(providers, "request_json", side_effect=RuntimeError("Cannot reach server")):
            response = self.call({"action": "models", "backend": providers.MODES[1], "local_provider": "LM Studio"})
            self.assertEqual(response.status, 400)
            self.assertEqual(response.payload, {"error": "Cannot reach server"})


class CoverTests(unittest.TestCase):
    def test_disabled_cover_needs_no_image_and_touches_no_files(self):
        node = artwork.SaveImageSmartPrefix()
        with patch.object(artwork, "_image_tensor_to_pil", side_effect=AssertionError("No image processing")), patch.object(artwork, "_resolve_prefix", side_effect=AssertionError("No filesystem")):
            self.assertEqual(node.check_lazy_status(enabled=False), [])
            self.assertEqual(node.save(None, "", "error_if_exists", False, 95, enabled=False), ("",))
        self.assertEqual(node.check_lazy_status(), ["image"])
        self.assertEqual(node.check_lazy_status(image=object()), [])
        self.assertTrue(artwork.SaveImageSmartPrefix.INPUT_TYPES()["required"]["image"][1]["lazy"])

    def test_cover_defaults_on_and_has_single_control_for_download_and_save(self):
        self.assertEqual(artwork.MiniMaxCoverControl().configure(), (True,))
        path = Path(__file__).resolve().parents[1] / "example_workflows/MiniMax_Music3_Production_Toolkit.json"
        workflow = json.loads(path.read_text(encoding="utf8"))
        nodes = {n["id"]: n for n in workflow["nodes"]}
        control = next(n for n in nodes.values() if n["type"] == "MiniMaxCoverControl")
        self.assertTrue(control["widgets_values_named"]["enabled"])
        links = [l for l in workflow["links"] if l[1] == control["id"]]
        self.assertEqual({(nodes[l[3]]["type"], nodes[l[3]]["inputs"][l[4]]["name"]) for l in links},
                         {("SaveImageSmartPrefix", "enabled"), ("MiniMaxModelAutodownload", "flux2_models")})
        preflight = next(n for n in nodes.values() if n["type"] == "MiniMaxModelAutodownload")
        self.assertFalse(preflight["widgets_values_named"]["llm_model"])
        self.assertFalse(any(n["type"] == "MiniMaxLLMSessionId" for n in nodes.values()))


class SessionMigrationTests(unittest.TestCase):
    def test_removal_keeps_other_links_and_source_seed_output(self):
        from workflow_schema import migrate_workflow
        for object_links in (False, True):
            graph = {"nodes": [
                {"id": 1, "type": "MiniMaxLLMSessionId", "outputs": [{"name": "session_id", "links": [10]}, {"name": "seed", "links": [12]}]},
                {"id": 2, "type": "MiniMaxLLMChat", "inputs": [{"name": "user_text", "link": None}, {"name": "session_id", "link": 10}, {"name": "system_prompt", "link": 11}]},
                {"id": 3, "type": "Other", "outputs": [{"links": [11]}], "inputs": [{"link": 12}]},
            ], "links": [[10, 1, 0, 2, 1, "STRING"], [11, 3, 0, 2, 2, "STRING"], [12, 1, 1, 3, 0, "INT"]]}
            if object_links:
                fields = ["id", "origin_id", "origin_slot", "target_id", "target_slot", "type"]
                graph["links"] = [dict(zip(fields, link)) for link in graph["links"]]
            self.assertEqual(len(migrate_workflow(graph)), 1)
            self.assertEqual(graph["nodes"][0]["outputs"][0]["links"], [])
            self.assertEqual(graph["nodes"][0]["outputs"][1]["links"], [12])
            self.assertEqual(len(graph["links"]), 2)
            self.assertEqual(graph["links"][0]["target_slot"] if object_links else graph["links"][0][4], 1)
            self.assertEqual(migrate_workflow(graph), [])
