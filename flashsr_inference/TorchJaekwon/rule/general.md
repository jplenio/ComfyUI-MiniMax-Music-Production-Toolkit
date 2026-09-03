# General code rules

Reusable, tool-agnostic rules for writing and reviewing code in any project that
depends on `torch_jaekwon`.

How to use: when writing or reviewing code, treat each rule below as a checklist
— satisfy every rule that applies, and when reviewing, report item by item what
is present, what is missing, and where.

Structure: `##` is a big category, `###` is a specific rule inside it. Numbers
(e.g. "1.1") are stable handles so you can say "check rule 1.1". Add new big
categories as `## 2.`, `## 3.`, ... as the need arises.

---

## 1. Type annotations

Annotate **at first definition** — the goal is that the type is clear where a
name is introduced, without forcing the reader (or the checker) to guess.

### 1.1 Always annotate signatures and attributes

- **Function parameters and return types** — always. This is the
  highest-value annotation and the one tools rely on most.
- **`self` / class attributes** — annotate at first definition (typically in
  `__init__`). This is *mandatory* when the right-hand side hides the real type,
  the classic case being attributes initialized to `None`
  (`self._model: Optional[Model] = None`), where the checker cannot otherwise
  infer the intended type.
- If an annotation needs a heavy/optional import, keep that import lazy and put
  the type behind `if TYPE_CHECKING:` (combined with
  `from __future__ import annotations`) so runtime behavior is unchanged.

### 1.2 Annotate locals only when the type isn't obvious

Let local variables be **inferred** by default — that matches idiomatic Python
and how `mypy` / `pyright` are designed. Add an annotation at first definition
only when inference is ambiguous or impossible:

- empty or ambiguous containers: `items: list[str] = []`
- a `None` start that will later hold a value: `cache: Optional[Cache] = None`
- expressions whose type is genuinely hard to read, or when you deliberately
  want to widen/narrow the type.

Do **not** annotate a local whose type is already obvious from the right-hand
side (e.g. `name: str = obj.get_name()`) — the annotation is redundant noise,
duplicates what the checker already infers, and can silently drift out of sync
with the value. The inferred type cannot drift; a hand-written one can.

---

## 2. Naming

A reader must know what a name holds within a few seconds, without jumping to its
definition. Review by reading, not by running.

### 2.1 Reuse the file's existing word before inventing one

Search for how the file already says it. A more literally-accurate new term costs the
reader a new concept.


---

## 3. Comments

### 3.1 One line

State the fact once, where it is owned. No multi-line rationale blocks, no restating
the code. Docstrings carry the contract; inline comments carry one-line constraints.

### 3.2 Delete comments that explain absent code

A comment justifying why something is *not* there is noise to a fresh reader.

---

## 4. Structure

### 4.1 Define next to first use

Don't compute a value one section above where it is consumed.

### 4.2 One condition, one block

Branches testing the same thing belong together; don't spell the same condition two
ways (`if mode == "audio"` here, `if mask is not None` there).

### 4.3 One rule, one implementation

Never express the same logic twice (train vs inference, batched vs 1-D). Share the
function and adapt shapes at the call site — parallel implementations drift silently.

### 4.4 No dead code, no thin wrappers

Delete no-op lines and unused computation. A wrapper that only adds a comparison
should be inlined so every call site reads the same.
