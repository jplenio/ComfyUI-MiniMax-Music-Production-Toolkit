# Agent behavior rules

Reusable, tool-agnostic rules for how an AI coding agent should work in any
project that depends on `torch_jaekwon`.

How to use: treat each rule below as a checklist — follow every rule that
applies.

Structure: `##` is a big category, `###` is a specific rule inside it. Numbers
(e.g. "1.1") are stable handles so you can say "check rule 1.1". Add new big
categories as `## 3.`, `## 4.`, ... as the need arises.

---

## 1. Explaining and citing code

### 1.1 Explain existing code intuitively, anchored to the code

When explaining the logic of existing code, always:

- **Explain intuitively first** — describe what the code does and *why* (the
  intent / mental model), not a line-by-line paraphrase of syntax.
- **Point to the exact code** — for each piece of logic, cite the specific file
  and lines so the user can see where it lives.
- **Show the code** — include the relevant snippet in a code-reference block
  (start/end line + filepath) so the explanation sits next to the implementation.

Do not explain logic in the abstract without showing the code it refers to.

### 1.2 Cite project-relative paths

When pointing the user at code, cite the **project-relative path with line
number** (e.g.
`nemo/collections/speechlm2/models/calm_interleaved.py:54`), rooted at the
project root. No absolute paths needed.

### 1.3 Walk through changes for review one file at a time

When the user wants to review newly added or changed code, present it as a
guided walkthrough, not a file dump:

- **One file per turn, numbered `N/total`.** List the full review order up front
  (so the scope is clear), then show one file at a time and pause for questions
  before moving on. Order from most load-bearing (core logic) to least (configs,
  tooling); flag trivial or out-of-scope files so the user can skip them.
- **For each file give three things, in this order:**
  1. the code — full if short, the key hunks if long — with inline `←` annotations
     on the lines that matter;
  2. **What it does** — the intent and how it fits / what changed vs the baseline
     (intuitive, per 1.1), not a line-by-line paraphrase;
  3. **Key points to check** — the non-obvious invariants or assumptions a reviewer
     should verify (e.g. "relies on X already being target-only", "separate output
     dir ⇒ no overwrite"), not a restatement of the code.
- Lead with the conclusion, keep it scannable, and end each file with a clear
  hand-back (e.g. "question, or next?").

## 2. Making changes

### 2.1 Show the plan and get confirmation before multi-file changes

Before creating or editing many different files (a new feature, a new
module/dir layout, anything touching several files at once), FIRST present the
proposed file/directory structure — which files will be created vs edited, and a
one-line purpose for each — and WAIT for the user's explicit confirmation before
writing any code.

- Exploration (reading/searching files, answering questions) needs no
  confirmation — only the actual file writes/edits do.
- For a trivial single-file change, just do it; this rule targets multi-file work.
- Surface the open design decisions alongside the structure (use the question
  tool) so they can be resolved before, not after, implementation.

## Code review

Writing or reviewing code: follow `rule/code_review.md` — it applies always, to my own code as well as
code I review.
