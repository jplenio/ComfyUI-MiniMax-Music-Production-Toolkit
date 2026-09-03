# Code review rules

Checklist for reviewing code. `##` is a category, `###` a rule; numbers are stable handles
("check 2.3"). Applies to code I write as well as code I review.

## 1. Readability first
### 1.1
A human must understand the code quickly on first read. When rules conflict, pick the more
readable option.

## 2. Naming
### 2.1
Names are explicit, never implicit: what it is and what type it holds is clear at a glance.
### 2.2
Match the naming style already in the file. If the existing style is bad, ask whether to rename
all of it rather than adding a second style.
### 2.3
Order names general → specific, so variants of one concept share a prefix and group together
when sorted or grepped: `is_audio_prompt` / `is_audio_generated`, not `prompt_is_audio` /
`generated_is_audio`.

Judge "general" by what you would search for. A family that already reads the other way
(`prediction_dir`, `transcript_dir` — English puts the head noun last) stays as it is; 2.2 wins
over 2.3.
### 2.4
Annotate the type at first definition.

## 3. Structure
### 3.1
No duplication, of code or of values. Extract repeated code into a shared function and reuse it;
refactoring existing code to do so is fine. A constant defined in two places is a bug even while
the copies agree — one must import the other.
### 3.2
Do not over-modularize. Splitting that hurts readability is worse than the duplication.

## 4. Comments
### 4.1
One concise line, wherever a comment is possible at all. Say the constraint the code cannot
show; do not restate what the code already says or explain history.

## 5. Defensive code
### 5.1
No assertions for failures that are highly unlikely. Guard real cases only.
