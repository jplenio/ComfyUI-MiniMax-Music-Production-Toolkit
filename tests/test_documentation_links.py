"""Every relative documentation link must resolve, including its anchor.

The repository ships a lot of cross-referenced documentation, and nothing checked
it: a moved file or a renamed heading produced a silently dead link. This test
resolves every relative markdown link and reference-style link against the file
that contains it, and checks that the ``#fragment`` exists as a heading in the
target.
"""
from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
# Generated sound-sample descriptions and GitHub templates are not part of the
# cross-referenced documentation set: the first contains ABC notation that looks
# like markdown links, the second is reached through GitHub's own UI.
SKIP_PARTS = {".git", "node_modules", "__pycache__", ".scratch", "dist", ".mypy_cache",
              "flashsr_inference", "third_party", "assets", ".github"}

# [text](target) and [label]: target
INLINE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
REFERENCE = re.compile(r"^\s*\[[^\]]+\]:\s*(\S+)", re.M)
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$", re.M)
# ABC notation and similar content can look like a markdown link; a real path
# never contains these characters.
NOT_A_PATH = re.compile(r"[|{}\\]")


def link_targets(text: str):
    """Relative link targets in *text*, ignoring absolute URLs and non-paths."""
    for target in INLINE.findall(text) + REFERENCE.findall(text):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        if NOT_A_PATH.search(target) or target.startswith("?"):
            continue
        yield target


def markdown_files():
    for path in sorted(ROOT.rglob("*.md")):
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        yield path


def slug(text: str) -> str:
    """GitHub's heading anchor: lowercase, punctuation dropped, spaces to dashes."""
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w\s\-]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", "-", text).strip("-")


def anchors_of(path: pathlib.Path) -> set:
    text = path.read_text(encoding="utf-8")
    return {slug(match.group(2)) for match in HEADING.finditer(text) if slug(match.group(2))}


class DocumentationLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.anchor_cache = {}

    def test_every_relative_link_resolves(self):
        problems = []
        for path in markdown_files():
            text = path.read_text(encoding="utf-8")
            targets = list(link_targets(text))
            for target in targets:
                relative, _, fragment = target.partition("#")
                if not relative:
                    continue
                resolved = (path.parent / relative).resolve()
                if not resolved.exists():
                    problems.append(f"{path.relative_to(ROOT).as_posix()} -> {target}")
                    continue
                if fragment and resolved.suffix.lower() == ".md":
                    anchors = self.anchor_cache.setdefault(resolved, anchors_of(resolved))
                    if fragment.lower() not in anchors:
                        problems.append(
                            f"{path.relative_to(ROOT).as_posix()} -> {target} (no such heading)")
        self.assertEqual(problems, [], "dead documentation links:\n" + "\n".join(problems))

    def test_the_documentation_layout_is_the_intended_one(self):
        root_docs = {path.name for path in ROOT.glob("*.md")}
        # GitHub-conventional files stay at the root; topic docs live in docs/.
        self.assertEqual(
            root_docs,
            {"README.md", "CHANGELOG.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md",
             "SECURITY.md", "NOTICE.md", "INSTALLATION.md", "TROUBLESHOOTING.md",
             "DEVELOPMENT.md", "PUBLISHING.md", "RELEASE_NOTES_v1.0.x.md",
             "RELEASE_NOTES_v2.x.md", "RELEASE_NOTES_v3.0.0.md", "RELEASE_NOTES_v3.0.1.md",
             "RELEASE_NOTES_v3.1.0.md"})
        for name in ("WORKFLOW.md", "YUE2.md", "AUDIO_PIPELINE.md", "LLM_PROVIDERS.md",
                     "PROMPT_LIBRARY.md"):
            self.assertTrue((ROOT / "docs" / name).is_file(), f"docs/{name} is missing")
        # The working handoff files are gitignored, so a fresh checkout has neither of
        # them - asserting their presence failed the first Linux CI run. Where they do
        # exist they must sit in docs/ like every other topic document, never at the
        # root.
        for name in ("PROJECT_STATE.md", "KONTEXT.md"):
            self.assertFalse((ROOT / name).exists(), f"{name} belongs in docs/, not at the root")
            if (ROOT / "docs" / name).exists():
                self.assertTrue((ROOT / "docs" / name).is_file(), f"docs/{name} is not a file")

    def test_every_markdown_file_is_reachable(self):
        """Topic documents under docs/ must be linked from somewhere.

        Node pages in ``web/docs`` are reached by their file name (ComfyUI serves
        them by node type, checked in test_node_documentation.py) and the root
        files by GitHub conventions, so both are out of scope here. Working and
        one-off documents are listed as deliberately unreferenced.
        """
        deliberately_unlinked = {
            "KONTEXT.md", "PROJECT_STATE.md", "REFACTOR-PLAN.md", "IMPROVE-TODO.md",
            "REDDIT_POST_v3.0.0.md", "REDDIT_POST_v3.0.1.md",
        }
        linked = set()
        for path in markdown_files():
            text = path.read_text(encoding="utf-8")
            for target in link_targets(text):
                relative = target.split("#")[0]
                resolved = (path.parent / relative).resolve()
                if resolved.suffix.lower() == ".md":
                    linked.add(resolved)
        orphans = []
        for path in sorted((ROOT / "docs").glob("*.md")):
            if path.name in deliberately_unlinked:
                continue
            if path.resolve() not in linked:
                orphans.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(orphans, [], "topic documents nobody links to: " + ", ".join(orphans))


if __name__ == "__main__":
    unittest.main()
