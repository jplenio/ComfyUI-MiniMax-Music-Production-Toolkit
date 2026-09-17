"""Dependencies must be declared, detected and documented.

A fresh ComfyUI installation is the normal case for a new user, so a third-party
import that nobody installs is a broken first start. This test walks every module of
the toolkit, classifies each external import, and requires that:

* everything the toolkit imports is either installed by a requirements file,
  provided by ComfyUI, or an optional engine that has a fallback;
* every optional engine is listed in ``capabilities.CAPABILITIES``, so the startup
  report names it with the command that installs it;
* the installation guide mentions each of them.
"""
from __future__ import annotations

import ast
import importlib
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

from _toolkit_bootstrap import load_entry_point  # noqa: E402

STDLIB = set(sys.stdlib_module_names) | {"__future__"}

# Imported by ComfyUI, never by us.
COMFY_PROVIDED = {
    "torch", "torchaudio", "torchvision", "folder_paths", "nodes", "comfy", "comfy_execution",
    "comfy_aimdo", "server", "aiohttp", "safetensors", "transformers", "yaml", "cv2", "PIL",
    "einops",
}

# Imported inside a function, with a documented fallback, and either tiny or
# deliberately not forced on users. ``capabilities.py`` reports the missing ones.
OPTIONAL_WITH_FALLBACK = {"llama_cpp", "psutil", "soxr", "tokenizers", "safetensors", "PIL",
                          "comfy_aimdo", "faster_whisper"}

SKIP_DIRS = {"flashsr_inference", "third_party", ".scratch", "__pycache__"}


def module_files():
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def local_modules():
    names = {path.stem for path in ROOT.glob("*.py")}
    names |= {path.stem for path in (ROOT / "scripts").glob("*.py")}
    names |= {path.stem for path in (ROOT / "tests").glob("*.py")}
    names |= {"tests", "third_party", "flashsr_inference", "prompts", "resources"}
    # Vendored inference code ships inside flashsr_inference/.
    names |= {"FlashSR", "TorchJaekwon", "AudioSR"}
    return names


def external_imports(path, local):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    eager, lazy = set(), set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            eager.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            eager.add(node.module.split(".")[0])
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            lazy.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            lazy.add(node.module.split(".")[0])
    keep = lambda names: {n for n in names
                          if n not in STDLIB and n not in local and not n.startswith("_")}
    eager = keep(eager)
    return eager, keep(lazy) - eager


def declared_requirements():
    names = set()
    for name in ("requirements.txt", "requirements-whisper.txt"):
        for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            module = re.split(r"[<>=!\[;]", line)[0].strip().lower()
            names.add(module.replace("_", "-"))
    return names


class DependencyDeclarationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pkg, _ = load_entry_point()
        cls.capabilities = importlib.import_module(cls.pkg.__name__ + ".capabilities")
        cls.local = local_modules()
        cls.declared = declared_requirements()

    def test_every_external_import_is_accounted_for(self):
        known_aliases = {"imageio_ffmpeg": "imageio-ffmpeg", "PIL": "pillow",
                         "faster_whisper": "faster-whisper"}
        unknown = {}
        for path in module_files():
            eager, lazy = external_imports(path, self.local)
            for name in eager | lazy:
                if name in COMFY_PROVIDED or name in OPTIONAL_WITH_FALLBACK:
                    continue
                package = known_aliases.get(name, name).lower().replace("_", "-")
                if package in self.declared:
                    continue
                unknown.setdefault(name, set()).add(path.relative_to(ROOT).as_posix())
        self.assertEqual(
            unknown, {},
            "undeclared third-party imports: "
            + "; ".join(f"{name} ({', '.join(sorted(where))})" for name, where in sorted(unknown.items())))

    def test_required_capabilities_are_installed_by_requirements(self):
        for capability in self.capabilities.CAPABILITIES:
            if not capability.required:
                continue
            package = {"PIL": "pillow", "imageio_ffmpeg": "imageio-ffmpeg"}.get(
                capability.module, capability.module).lower().replace("_", "-")
            self.assertIn(package, self.declared,
                          f"{capability.module} is required but not in a requirements file")

    def test_the_whisper_engine_ships_in_the_main_requirements(self):
        """3.1 presents the instrumental check as a feature, so its engine installs by default."""
        text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("faster-whisper", text)
        self.assertIn("requirements-whisper.txt", text,
                      "the minimal-install escape hatch must be named")

    def test_every_optional_engine_is_detected_and_named(self):
        modules = {capability.module for capability in self.capabilities.CAPABILITIES}
        self.assertTrue({"faster_whisper", "llama_cpp", "psutil", "soxr"} <= modules)

    def test_the_installation_guide_mentions_every_capability(self):
        text = (ROOT / "INSTALLATION.md").read_text(encoding="utf-8").lower()
        for capability in self.capabilities.CAPABILITIES:
            needle = capability.module.lower().replace("_", "-")
            alias = {"imageio-ffmpeg": "imageio-ffmpeg", "pil": "pillow",
                     "faster-whisper": "faster-whisper", "llama-cpp": "llama-cpp-python"}.get(
                needle, needle)
            self.assertIn(alias, text, f"INSTALLATION.md does not mention {capability.module}")

    def test_detection_does_not_import_the_engine(self):
        self.assertNotIn("faster_whisper", sys.modules,
                         "the capability check must not import the Whisper engine")

    def test_a_missing_module_is_reported_and_a_present_one_is_not(self):
        real = self.capabilities.is_available
        try:
            self.capabilities.is_available = lambda name: name != "soxr"
            required, optional = self.capabilities.missing_capabilities()
            self.assertEqual(required, [])
            self.assertEqual([c.module for c in optional], ["soxr"])
            lines = self.capabilities.capability_lines()
            self.assertEqual(len(lines), 1)
            self.assertIn("soxr", lines[0])
            self.assertIn("pip install soxr", lines[0])

            self.capabilities.is_available = lambda name: name != "scipy"
            required, optional = self.capabilities.missing_capabilities()
            self.assertEqual([c.module for c in required], ["scipy"])
            self.assertIn("requirements.txt", self.capabilities.capability_lines()[0])
        finally:
            self.capabilities.is_available = real

    def test_a_clean_installation_says_so(self):
        real = self.capabilities.is_available
        try:
            self.capabilities.is_available = lambda name: True
            self.assertEqual(
                self.capabilities.capability_lines(),
                ["All optional engines are installed; every feature is available."])
        finally:
            self.capabilities.is_available = real


if __name__ == "__main__":
    unittest.main()
