---
description: How to find the shared torch_jaekwon package and its cross-project rule docs
alwaysApply: true
---

# torch_jaekwon: shared single-source rules

`torch_jaekwon` is the shared package, used across projects, that holds the
reusable rules (and utilities) — the single source of truth. Do **not** duplicate
those rules in this repo; read them from the package and, when a shared rule needs
to change, edit the file in `torch_jaekwon` (not here).

## Locate the package (path-independent, works on any server)

`torch_jaekwon` is installed in a specific Python env, so run the locate command
with that env's interpreter — the bare login-node `python` usually won't have it:

```bash
python -c "import torch_jaekwon, os; print(os.path.dirname(os.path.dirname(torch_jaekwon.__file__)))"
```

If that fails with `ModuleNotFoundError`, do **not** guess the env. List the
available environments and ask the user (via the question tool) which one to use,
then retry the locate command with it (`<env>/bin/python -c "..."` or after
`conda activate <env>`):

```bash
conda env list
```

The printed directory holds the rule docs under `rule/`.

## Rule docs to read (apply when writing or reviewing code)

- `rule/train.md` — **training** rules (resume/checkpointing, dataloader state,
  etc.). Read and apply when asked to write or review training code.
- `rule/general.md` — **general code-style** rules (e.g. the type-annotation
  convention). Read and apply when writing or reviewing code.
- `rule/agent.md` — **agent behavior** rules (how to explain/cite code, when to
  confirm before multi-file changes). Read and apply when working as a coding agent.

## Keep this rule in sync

This rule is kept as `rule/torch-jaekwon.md` in the `torch_jaekwon` package (the
copy-me template for new projects) and mirrored into each project as
`.cursor/rules/torch-jaekwon.mdc`. When you change one, update the other.
