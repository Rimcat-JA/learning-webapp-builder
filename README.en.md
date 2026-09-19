# Learning Webapp Builder — Release 1.0.0

[日本語](README.md) | **English**

A skill that lets an AI carry a learning web app all the way from curriculum design, through questions and explanations, implementation, functional verification, and delivery of a localhost build. It reflects the 15 requirement answers gathered during planning. Subject area and question count are not fixed.

## Getting started

1. Unzip the archive and place the `learning-webapp-builder` folder somewhere the AI can read.
2. In Codex CLI / IDE, open that location. In ChatGPT Work, attach a ZIP containing the folder plus your source material so the files are readable.
3. Send the following instruction:

```text
Read learning-webapp-builder/SKILL.md and follow this skill to build a complete learning web app.

Subject: [what to learn]
Learners and prior knowledge: [starting level]
Learning goals: [what they should be able to do]
Source material: [attached files / existing app / create from scratch]
Desired volume: [number of questions or study hours; say if the AI may propose]

Make it a localhost build, Windows first.
Do not widen the publishing scope without confirmation.
Do not re-ask conditions that are already clear; decide implementation details yourself and proceed to completion.
```

To enable automatic invocation, register the `learning-webapp-builder` folder with your environment's skill registration feature. `SKILL.md` is the entry point. Registration steps and storage locations differ by environment; receiving this ZIP alone does not register anything. The direct-read instruction above works even in environments without a registration feature.

## What's included

| Location | Contents |
|---|---|
| `learning-webapp-builder/SKILL.md` | Working procedure and completion criteria for the AI |
| `schemas/` | JSON Schemas for course, questions, and progress |
| `scripts/course_tools.py` | Reference grader for six question formats; course and progress validation |
| `scripts/check_migration.py` | Migration-plan checker that protects question IDs and history |
| `examples/` | An 8-question sample course covering all six formats plus unverified branches, and progress for two learners |
| `tests/` | Automated tests for normal, error, boundary, and history-migration cases |
| `references/` | Details on requirements, curriculum design, UI, storage/sync, revisions, verification, and delivery |
| `RELEASE_REPORT.md` | Verification results for the skill itself |

Paths such as `schemas/` are relative to `learning-webapp-builder/`. The 8 sample questions demonstrate the common format; they do not prescribe the question count or difficulty of courses you build.

## Running the bundled tools

Python 3.10 or later is recommended. The bundled grading, validation, and migration tools and the standard tests need no extra packages. Learners never touch Python; these tools are for the AI and developers building the app.

On Windows, open a terminal in the extracted folder and run:

```powershell
cd learning-webapp-builder
py -3 scripts/course_tools.py validate examples/course.json --progress examples/progress.json --json
py -3 -m unittest discover -s tests -v
```

On macOS / Linux, replace `py -3` with `python3`. Files are UTF-8. If output looks garbled in your terminal, set `PYTHONIOENCODING=utf-8`.

Validation emits warnings for the two unverified sample questions. This is expected: the contract is to include unverified questions visibly in the app rather than silently dropping them.

## Grading and storage defaults

- Supports single choice, multiple choice, numeric input, choice-based fill-in-the-blank, ordering, and one-to-one matching.
- Learners are never asked to write code or free text. Runtime AI grading is not assumed.
- Multiple choice is graded as an order-independent exact match; other non-numeric formats are graded as whole-answer matches by default. Partial credit requires an additional specification and tests.
- Numeric answers accept half-width finite numbers. Tolerance is the larger of absolute and relative error. Full-width digits, units, and thousands separators are handled by the UI before reaching the reference grader.
- Unverified questions with a provisional answer are graded provisionally; those without one are held. Neither is mixed into confirmed scores.
- Combines browser storage, a local DB, and authenticated sync. When no sync target exists, the app shows "not connected" and local study, saving, and backup remain usable.
- Past history is never re-graded or overwritten after a question is updated.

## Example request for revising an existing app

```text
Use this skill to revise the attached learning app.
Keep the original question IDs and learner progress, and create a backup before changing anything.
Changes: [what to change]
Convert the course and progress to the common format, check the migration plan,
verify screens, grading, and save/restore, then deliver a localhost build.
Do not publish it.
```

## Sample: Python 360 (an app built with this skill)

As an example of this skill's output, the repository includes **Python 360**, a 36-chapter, 360-question Python code-reading practice app.

- Source: [`samples/python360-web/`](samples/python360-web/)
- ZIP: `python360-web.zip` under [Releases](../../releases)

To run it, execute `python server.py` (or `node server.mjs`; `start.bat` on Windows) inside `samples/python360-web/` and open `http://localhost:4173`. No extra packages or build step are required. See [`samples/python360-web/README.md`](samples/python360-web/README.md) for details.

## Version control

The initial release is recorded in Git and also shipped as a Git bundle. When building a course, manage changes separately in the generated app's own repository. There is no need to import this skill's sample data as real learner data.
