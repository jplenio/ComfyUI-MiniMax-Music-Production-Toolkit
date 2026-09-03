"""Headless ComfyUI smoke test for the bundled example workflow (maintainer tool).

Starts a throwaway ComfyUI instance against an isolated base directory whose
custom_nodes folder links to this repository, verifies node registration,
submits the public example workflow in API form (with subgraph inlining, the
LLM section disabled and manual parser fallbacks), and reports how far
execution gets.

Expected outcome: the graph is accepted without validation errors and the run
reaches the MiniMax/FLUX model loaders, which fail cleanly because the test
base directory contains only empty placeholder model files (auto-download is
disabled).

Usage (from a machine with a ComfyUI checkout):

    python scripts/comfyui_smoke_test.py \
        --comfy-dir D:/ComfyUI \
        --venv-python D:/ComfyUI/.venv/Scripts/python.exe \
        --base-dir %TEMP%/minimax_smoke_v2

The script creates a junction ``<base-dir>/custom_nodes/ComfyUI-MiniMax-Music-Production-Toolkit``
pointing at this repository, so no changes to the real ComfyUI installation
are needed.  The junction and the base directory are removed afterwards
(keep them with ``--keep-base-dir``).
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

EXPECTED_TOOLKIT_NODES = {
    "MiniMaxStructuredPromptV20",
    "MiniMaxLLMChat",
    "MiniMaxLLMUnload",
    "MiniMaxFlashSRAudio",
    "MiniMaxModelAutodownload",
    "MiniMaxParseExternalLLMOutputV16",
    "MiniMaxLLMSessionId",
    "MiniMaxSaveProductionJSON",
    "MiniMaxLLMTemplateV16",
}


def http_json(url, data=None, timeout=60):
    request = urllib.request.Request(url, method="POST" if data is not None else "GET")
    if data is not None:
        request.add_header("Content-Type", "application/json")
        request.data = json.dumps(data).encode("utf-8")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {body[:3000]}")
        raise


def wait_ready(timeout=240):
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            http_json(f"{BASE_URL}/system_stats", timeout=5)
            return True
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2)
    raise SystemExit(f"ComfyUI did not become ready: {last_error}")


def to_api_format(workflow):
    """Convert the UI-format workflow into the API prompt, inlining subgraph
    instances the same way the ComfyUI frontend does (flattened ids)."""
    definitions = {d["id"]: d for d in workflow.get("definitions", {}).get("subgraphs", [])}
    nodes = {n["id"]: n for n in workflow["nodes"]}
    links = {link[0]: link for link in workflow["links"]}

    # Subgraph instance outputs are produced by inner nodes; map
    # (instance_id, output_slot) -> (flattened_inner_id, inner_slot).
    output_map = {}
    for node_id, node in nodes.items():
        if node.get("type") not in definitions:
            continue
        definition = definitions[node["type"]]
        inner_links = {link["id"]: link for link in definition.get("links", [])}
        for slot, boundary in enumerate(definition.get("outputs") or []):
            for link_id in boundary.get("linkIds") or []:
                inner = inner_links.get(link_id)
                if inner and inner["origin_id"] != definition["outputNode"]["id"]:
                    output_map[(node_id, slot)] = (f"{node_id}:{inner['origin_id']}", inner["origin_slot"])
                    break

    prompt = {}
    for node_id, node in nodes.items():
        if node.get("type") == "MarkdownNote":
            continue
        if node["type"] in definitions:
            _inline_subgraph(node, definitions[node["type"]], links, prompt)
            continue
        inputs = {}
        widget_values = list(node.get("widgets_values") or [])
        for entry in node.get("inputs", []):
            name = entry.get("name")
            link_id = entry.get("link")
            has_widget = "widget" in entry
            value = widget_values.pop(0) if (has_widget and widget_values) else None
            if link_id is not None:
                outer = links[link_id]
                origin = output_map.get((outer[1], outer[2]), (str(outer[1]), outer[2]))
                inputs[name] = [origin[0], origin[1]]
            elif has_widget and value is not None:
                inputs[name] = value
        prompt[str(node_id)] = {"class_type": node["type"], "inputs": inputs}
    return prompt


def _inline_subgraph(instance, definition, outer_links, prompt):
    prefix = str(instance["id"])
    inner_links = {link["id"]: link for link in definition.get("links", [])}
    input_node_id = definition["inputNode"]["id"]
    output_node_id = definition["outputNode"]["id"]

    # Resolve every boundary input slot of the instance to its outer value.
    boundary_values = {}
    widget_values = list(instance.get("widgets_values") or [])
    for slot, entry in enumerate(instance.get("inputs", [])):
        link_id = entry.get("link")
        has_widget = "widget" in entry
        widget_value = widget_values.pop(0) if (has_widget and widget_values) else None
        if link_id is not None:
            outer = outer_links[link_id]
            boundary_values[slot] = ("link", str(outer[1]), outer[2])
        elif has_widget:
            boundary_values[slot] = ("value", widget_value)

    # Which inner link feeds which boundary input slot?
    slot_links = {}
    for slot, boundary in enumerate(definition.get("inputs") or []):
        if slot not in boundary_values:
            continue
        for link_id in boundary.get("linkIds") or []:
            slot_links[link_id] = boundary_values[slot]

    for inner in definition.get("nodes", []):
        flat_id = f"{prefix}:{inner['id']}"
        inputs = {}
        widget_values = list(inner.get("widgets_values") or [])
        for entry in inner.get("inputs", []):
            name = entry.get("name")
            link_id = entry.get("link")
            has_widget = "widget" in entry
            value = widget_values.pop(0) if (has_widget and widget_values) else None
            if link_id is not None:
                inner_link = inner_links.get(link_id)
                if inner_link is None:
                    raise SystemExit(f"subgraph {prefix}: dangling inner link {link_id}")
                if inner_link["origin_id"] == input_node_id:
                    resolved = slot_links.get(link_id)
                    if resolved and resolved[0] == "link":
                        inputs[name] = [resolved[1], resolved[2]]
                    elif resolved:
                        inputs[name] = resolved[1]
                elif inner_link["origin_id"] != output_node_id:
                    inputs[name] = [f"{prefix}:{inner_link['origin_id']}", inner_link["origin_slot"]]
            elif has_widget and value is not None:
                inputs[name] = value
        prompt[flat_id] = {"class_type": inner["type"], "inputs": inputs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy-dir", required=True, help="path to a ComfyUI checkout")
    parser.add_argument("--venv-python", required=True, help="Python of the ComfyUI venv")
    parser.add_argument("--base-dir", required=True, help="throwaway base directory (junction created inside)")
    parser.add_argument("--port", type=int, default=18188)
    parser.add_argument("--keep-base-dir", action="store_true", help="keep the base directory after the test")
    args = parser.parse_args()

    global COMFY_DIR, VENV_PYTHON, BASE_DIR, PORT, BASE_URL
    COMFY_DIR = args.comfy_dir
    VENV_PYTHON = args.venv_python
    BASE_DIR = args.base_dir
    PORT = args.port
    BASE_URL = f"http://127.0.0.1:{PORT}"

    Path(BASE_DIR).mkdir(parents=True, exist_ok=True)
    junction = Path(BASE_DIR) / "custom_nodes" / "ComfyUI-MiniMax-Music-Production-Toolkit"
    try:
        if not junction.exists():
            junction.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(junction), str(REPO)],
                check=True, capture_output=True,
            )

        # Empty placeholder model files so the loader COMBOs populate and the graph
        # passes validation; execution then reaches the loaders and fails cleanly
        # on the (empty) files, proving the whole prompt/LLM section ran.
        for relative in (
            "diffusion_models/minimax_music3_dit_fp16.safetensors",
            "text_encoders/minimax_music3_text_encoder_pruned_int8_convrot.safetensors",
            "vae/minimax_music3_dav.safetensors",
            "diffusion_models/flux-2-klein-4b.safetensors",
            "text_encoders/qwen_3_4b.safetensors",
            "vae/flux2-vae.safetensors",
        ):
            placeholder = Path(BASE_DIR) / "models" / relative
            placeholder.parent.mkdir(parents=True, exist_ok=True)
            if not placeholder.exists():
                placeholder.write_bytes(b"")

        workflow = json.load(open(f"{REPO}/example_workflows/MiniMax_Music3_Production_Toolkit.json", encoding="utf-8"))
        api_prompt = to_api_format(workflow)

        # Test overrides: no downloads, LLM section off, manual fallback used.
        api_prompt["80"]["inputs"]["user_prompt_file"] = "house/melodic-house.txt"
        # The frontend copies the selected file's body into description_override;
        # set it explicitly here to mirror the real UI state (headless runs have
        # no JS prefill).
        api_prompt["80"]["inputs"]["description_override"] = "Smoke test description: warm melodic house groove."
        api_prompt["81"]["inputs"]["enabled"] = False
        api_prompt["81"]["inputs"]["auto_download"] = False
        api_prompt["45"]["inputs"]["auto_download"] = False
        api_prompt["101"]["inputs"]["auto_download"] = False
        api_prompt["53"]["inputs"]["manual_caption"] = "Smoke test caption: warm melodic house groove."
        api_prompt["53"]["inputs"]["manual_lyrics"] = "[Intro]\n[Build]\n[Drop]"
        api_prompt["53"]["inputs"]["manual_title"] = "Smoke Test Song"

        log_path = f"{BASE_DIR}/comfy_smoke.log"
        with open(log_path, "w", encoding="utf-8", newline="\n") as log:
            process = subprocess.Popen(
                [
                    VENV_PYTHON, "main.py",
                    "--base-directory", BASE_DIR,
                    "--listen", "127.0.0.1",
                    "--port", str(PORT),
                    "--cpu",
                    "--disable-auto-launch",
                    "--disable-metadata",
                ],
                cwd=COMFY_DIR,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        try:
            wait_ready()
            print("SMOKE: ComfyUI ready")

            object_info = http_json(f"{BASE_URL}/object_info", timeout=60)
            registered = set(object_info)
            missing = EXPECTED_TOOLKIT_NODES - registered
            print(f"SMOKE: toolkit node registration missing={sorted(missing) or 'none'}")
            for name in ("MiniMaxStructuredPromptV20", "MiniMaxLLMChat", "MiniMaxFlashSRAudio"):
                if name in object_info:
                    info = object_info[name]
                    inputs = info.get("input", {})
                    required = list(inputs.get("required", {}).keys())
                    optional = list(inputs.get("optional", {}).keys())
                    print(f"SMOKE: {name} required={required} optional={optional}")

            payload = {"prompt": api_prompt, "client_id": "smoke-test-v2"}
            result = http_json(f"{BASE_URL}/prompt", data=payload, timeout=120)
            prompt_id = result.get("prompt_id")
            print(f"SMOKE: prompt accepted, prompt_id={prompt_id}")

            history = {}
            deadline = time.time() + 600
            while time.time() < deadline:
                history = http_json(f"{BASE_URL}/history/{prompt_id}", timeout=30).get(prompt_id, {})
                status = history.get("status", {})
                if status.get("completed") or status.get("status_str") == "error":
                    break
                time.sleep(2)

            status = history.get("status", {})
            print(f"SMOKE: final status_str={status.get('status_str')}")
            messages = status.get("messages", [])
            for message in messages[:6]:
                print(f"SMOKE:   message: {message[0]}: {str(message[1])[:220]}")
            outputs = history.get("outputs", {})
            print(f"SMOKE: outputs so far: {sorted(outputs.keys(), key=lambda k: int(k) if str(k).isdigit() else 0)}")

            executed = set()
            error_node_types = set()
            for message in messages:
                if message[0] == "executed":
                    data = message[1] or {}
                    executed.add(str(data.get("node")))
                elif message[0] == "execution_error":
                    data = message[1] or {}
                    executed.update(str(n) for n in (data.get("executed") or []))
                    error_node_types.add(str(data.get("node_type") or ""))

            expected_loaders = {"VAELoader", "UNETLoader", "CLIPLoader"}
            stopped_at_loader = bool(error_node_types & expected_loaders)
            if "80" in executed:
                print("SMOKE: structured prompt node (80) executed OK")
            else:
                print("SMOKE: WARNING: structured prompt node (80) did not execute")
            if stopped_at_loader:
                print("SMOKE: expected stop at a model loader (empty placeholder model files)")
            else:
                print(f"SMOKE: NOTE: run stopped at {sorted(error_node_types) or 'unknown'}; expected a model loader with placeholder files")
        finally:
            process.terminate()
            try:
                process.wait(timeout=30)
            except Exception:
                process.kill()
    finally:
        if junction.exists():
            subprocess.run(["cmd", "/c", "rmdir", str(junction)], capture_output=True)
        if not args.keep_base_dir:
            shutil.rmtree(Path(BASE_DIR), ignore_errors=True)


if __name__ == "__main__":
    main()
