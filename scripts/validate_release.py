#!/usr/bin/env python3
"""Static release validation that intentionally does not import ComfyUI/Torch."""
from __future__ import annotations

import ast
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "README.md", "INSTALLATION.md", "WORKFLOW.md", "PROMPT_LIBRARY.md",
    "AUDIO_PIPELINE.md", "TROUBLESHOOTING.md", "PUBLISHING.md", "LICENSE",
    "NOTICE.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md",
    "CITATION.cff", "VERSION",
    "pyproject.toml", "requirements.txt", "__init__.py", "scripts/package_release.py",
    "example_workflows/MiniMax_Music3_Production_Toolkit.json",
    "prompts/system/minimax-music3-production.txt",
]
TEXT_EXTENSIONS = {".py", ".js", ".md", ".txt", ".toml", ".json", ".yml", ".yaml", ".bat"}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def check_required() -> None:
    required = list(REQUIRED)
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").exists() else ""
    if version:
        required.append(f"RELEASE_NOTES_v{version}.md")
    missing = [rel for rel in required if not (ROOT / rel).exists()]
    if missing:
        fail("Missing required files: " + ", ".join(missing))


def check_python_syntax() -> None:
    for path in sorted(ROOT.glob("*.py")):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            fail(f"Python syntax error in {path.name}: {exc}")


def check_pyproject() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data.get("project", {})
    comfy = data.get("tool", {}).get("comfy", {})
    if project.get("name") != "comfyui-minimax-music-production-toolkit":
        fail("Unexpected [project].name")
    if comfy.get("PublisherId") != "jplenio":
        fail("[tool.comfy].PublisherId must be jplenio for this release")
    if project.get("version") != (ROOT / "VERSION").read_text(encoding="utf-8").strip():
        fail("VERSION and pyproject.toml version differ")


def _validate_subgraph(subgraph: dict, errors: list[str], label: str) -> None:
    nodes = {n.get("id"): n for n in subgraph.get("nodes", [])}
    links = {l.get("id"): l for l in subgraph.get("links", []) if isinstance(l, dict)}
    input_id = (subgraph.get("inputNode") or {}).get("id")
    output_id = (subgraph.get("outputNode") or {}).get("id")
    valid_endpoints = set(nodes) | {x for x in (input_id, output_id) if x is not None}

    # Boundary declarations must point to real subgraph links.
    for boundary_kind in ("inputs", "outputs"):
        for slot, item in enumerate(subgraph.get(boundary_kind, []) or []):
            for lid in item.get("linkIds") or []:
                if lid not in links:
                    errors.append(f"{label} {boundary_kind}[{slot}] {item.get('name')}: dangling linkId {lid}")

    # Node input/output references must resolve inside this subgraph.
    for node_id, node in nodes.items():
        for slot, inp in enumerate(node.get("inputs", []) or []):
            lid = inp.get("link")
            if lid is not None and lid not in links:
                errors.append(f"{label} node {node_id} input[{slot}] {inp.get('name')}: dangling link {lid}")
        for slot, out in enumerate(node.get("outputs", []) or []):
            for lid in out.get("links") or []:
                if lid not in links:
                    errors.append(f"{label} node {node_id} output[{slot}] {out.get('name')}: dangling link {lid}")

    # Every stored link must connect valid real/virtual endpoints and valid slots.
    for lid, link in links.items():
        origin_id = link.get("origin_id")
        target_id = link.get("target_id")
        origin_slot = link.get("origin_slot")
        target_slot = link.get("target_slot")
        if origin_id not in valid_endpoints or target_id not in valid_endpoints:
            errors.append(f"{label} link {lid}: invalid endpoint {origin_id}->{target_id}")
            continue
        if origin_id == input_id:
            if not isinstance(origin_slot, int) or origin_slot >= len(subgraph.get("inputs", []) or []):
                errors.append(f"{label} link {lid}: invalid subgraph input slot {origin_slot}")
        elif origin_id in nodes:
            if not isinstance(origin_slot, int) or origin_slot >= len(nodes[origin_id].get("outputs", []) or []):
                errors.append(f"{label} link {lid}: invalid source slot {origin_slot}")
        if target_id == output_id:
            if not isinstance(target_slot, int) or target_slot >= len(subgraph.get("outputs", []) or []):
                errors.append(f"{label} link {lid}: invalid subgraph output slot {target_slot}")
        elif target_id in nodes:
            if not isinstance(target_slot, int) or target_slot >= len(nodes[target_id].get("inputs", []) or []):
                errors.append(f"{label} link {lid}: invalid destination slot {target_slot}")


def check_workflow() -> None:
    path = ROOT / "example_workflows/MiniMax_Music3_Production_Toolkit.json"
    wf = json.loads(path.read_text(encoding="utf-8"))
    node_map = {n["id"]: n for n in wf.get("nodes", [])}
    links = {l[0]: l for l in wf.get("links", [])}
    errors: list[str] = []
    for link_id, src, src_slot, dst, dst_slot, _type in wf.get("links", []):
        if src not in node_map or dst not in node_map:
            errors.append(f"link {link_id}: missing node")
            continue
        if src_slot >= len(node_map[src].get("outputs", [])):
            errors.append(f"link {link_id}: invalid source slot")
        if dst_slot >= len(node_map[dst].get("inputs", [])):
            errors.append(f"link {link_id}: invalid destination slot")
    for node in wf.get("nodes", []):
        for inp in node.get("inputs", []):
            lid = inp.get("link")
            if lid is not None and lid not in links:
                errors.append(f"node {node['id']} input {inp.get('name')}: dangling link {lid}")
        for out in node.get("outputs", []):
            for lid in out.get("links") or []:
                if lid not in links:
                    errors.append(f"node {node['id']} output {out.get('name')}: dangling link {lid}")

    definitions = wf.get("definitions") or {}
    for idx, subgraph in enumerate(definitions.get("subgraphs", []) or []):
        if isinstance(subgraph, dict):
            _validate_subgraph(subgraph, errors, f"subgraph[{idx}] {subgraph.get('name', subgraph.get('id', 'unnamed'))}")

    if errors:
        fail("Invalid example workflow: " + "; ".join(errors[:10]))
    if "MiniMaxLLMSessionId" not in {n.get("type") for n in wf.get("nodes", [])}:
        fail("Public workflow is missing MiniMaxLLMSessionId")
    if {"Number to Text", "Seed"} & {n.get("type") for n in wf.get("nodes", [])}:
        fail("Public workflow still depends on legacy utility nodes")


def check_prompt_library() -> None:
    user_files = [p for p in (ROOT / "prompts/user").rglob("*") if p.is_file() and p.suffix.lower() in {".txt", ".md", ".prompt"}]
    system_files = [p for p in (ROOT / "prompts/system").rglob("*") if p.is_file() and p.suffix.lower() in {".txt", ".md", ".prompt"}]
    if len(user_files) < 30:
        fail(f"Expected at least 30 bundled user prompts, found {len(user_files)}")
    if not system_files:
        fail("No bundled system prompts found")
    for path in user_files + system_files:
        if not path.read_text(encoding="utf-8-sig").strip():
            fail(f"Empty prompt file: {path.relative_to(ROOT)}")


def check_privacy_and_placeholders() -> None:
    # Generic leak patterns only: the repository deliberately contains the public
    # author name/GitHub URL, so those are not treated as privacy violations.
    bad_patterns = [
        re.compile(r"[A-Za-z]:\\\\Users\\\\[^\\\\\s\"']+", re.I),
        re.compile(r"[A-Za-z]:/Users/[^/\s\"']+", re.I),
        re.compile(r"(?:192\.168\.|10\.\d+\.\d+\.|172\.(?:1[6-9]|2\d|3[01])\.)\d+\.\d+"),
        re.compile("YOUR_" + "GITHUB_USERNAME|YOUR_" + "COMFY_PUBLISHER_ID"),
    ]
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if any(part in {".git", "__pycache__"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in bad_patterns:
            if pattern.search(text):
                fail(f"Potential private/placeholder data in {path.relative_to(ROOT)} matching {pattern.pattern}")


def check_node_docs() -> None:
    keys: set[str] = set()
    for path in ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "NODE_CLASS_MAPPINGS" and isinstance(node.value, ast.Dict):
                        for key_node in node.value.keys:
                            if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                                keys.add(key_node.value)
                    if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id == "NODE_CLASS_MAPPINGS":
                        sl = target.slice
                        if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                            keys.add(sl.value)
    missing = [key for key in sorted(keys) if not (ROOT / "web/docs" / f"{key}.md").exists()]
    if missing:
        fail("Missing node docs: " + ", ".join(missing))
    if len(keys) < 20:
        fail(f"Unexpectedly low registered node count discovered statically: {len(keys)}")


def main() -> None:
    check_required()
    check_python_syntax()
    check_pyproject()
    check_workflow()
    check_prompt_library()
    check_privacy_and_placeholders()
    check_node_docs()
    print("Release validation OK")


if __name__ == "__main__":
    main()
