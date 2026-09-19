#!/usr/bin/env python3
"""Plan a course migration without rewriting courses or learning records.

Usage: python check_migration.py OLD.json NEW.json [--progress PROGRESS.json]
       [--id-map ID_MAP.json] [--output REPORT.json]

ID_MAP is either {"old-id": "new-id"} or a list of
{"from": "old-id", "to": "new-id"} records. Unmapped IDs present in both
courses keep their identity. Renames are resolved through a versioned mapping;
original attempt records, scores, timestamps, and references remain immutable.

Exit codes: 0 = plan ready; 1 = unsafe/invalid migration blocked;
2 = malformed JSON, command-line, or file/tool error. This is a planning tool,
not a migration executor or a replacement for the full course validator.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from datetime import datetime
from typing import Any


class InputError(ValueError):
    """The supplied JSON cannot be interpreted as an input document."""


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise InputError(f"Non-finite JSON number: {value}")


def load_json(path: str | Path) -> Any:
    try:
        with Path(path).open(encoding="utf-8-sig") as handle:
            return json.load(handle, object_pairs_hook=_object,
                             parse_constant=_invalid_constant)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise InputError(f"Cannot read {path}: {exc}") from exc


def _identifier(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def _revision(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value
    ):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.tzinfo is not None and parsed.utcoffset() is not None
    except ValueError:
        return False


def _json_safe(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_json_safe(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_safe(item) for key, item in value.items())
    return False


def _canonical(value: Any) -> str:
    # JSON serialization keeps booleans distinct from integers in comparisons.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(",", ":"))


def build_plan(old: dict[str, Any], new: dict[str, Any],
               progress: dict[str, Any] | None = None,
               id_map: dict[str, str] | list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Return a dry-run report. Arguments are never mutated.

    Every question field except id/revision is compared conservatively. A change
    to any of those fields requires an increased revision. Historical attempts
    for older revisions are valid but are never regraded against a newer key.
    """
    for name, value in (("old", old), ("new", new), ("progress", progress)):
        if value is not None and (not isinstance(value, dict) or not _json_safe(value)):
            raise InputError(f"{name} must be a finite JSON object")
    if old is None or new is None:
        raise InputError("Both old and new course objects are required")
    if id_map is not None and not _json_safe(id_map):
        raise InputError("id-map must contain only finite JSON values")

    reasons: list[dict[str, str]] = []

    def block(code: str, path: str, message: str) -> None:
        reasons.append({"code": code, "path": path, "message": message})

    def course_index(course: dict[str, Any], prefix: str) -> dict[str, dict[str, Any]]:
        if course.get("schemaVersion") != "1.0":
            block("SCHEMA_VERSION", prefix + ".schemaVersion", "Expected schemaVersion '1.0'.")
        for field in ("id", "version"):
            if not _identifier(course.get(field)):
                block("INVALID_ID", prefix + "." + field, "Expected a nonempty trimmed string.")
        questions = course.get("questions")
        if not isinstance(questions, list):
            block("QUESTIONS_REQUIRED", prefix + ".questions", "questions must be an array.")
            questions = []
        index: dict[str, dict[str, Any]] = {}
        for number, question in enumerate(questions):
            path = f"{prefix}.questions[{number}]"
            if not isinstance(question, dict):
                block("INVALID_QUESTION", path, "Question must be an object.")
                continue
            identifier = question.get("id")
            if not _identifier(identifier):
                block("INVALID_QUESTION_ID", path + ".id", "Question ID must be nonempty and trimmed.")
                continue
            if identifier in index:
                block("DUPLICATE_QUESTION_ID", path + ".id", f"Duplicate question ID {identifier!r}.")
                continue
            index[identifier] = question
            if not _revision(question.get("revision")):
                block("INVALID_REVISION", path + ".revision", "revision must be an integer of at least 1.")
            if not _identifier(question.get("type")):
                block("INVALID_QUESTION_TYPE", path + ".type", "Question type must be nonempty.")
            required_fields = ["prompt", "explanation"]
            verification = question.get("verification")
            if not isinstance(verification, dict) or verification.get("status") != "unverified":
                required_fields.append("answer")
            for field in required_fields:
                if field not in question:
                    block("MISSING_QUESTION_FIELD", path + "." + field, f"Missing {field}.")
        chapters = course.get("chapters")
        if not isinstance(chapters, list):
            block("CHAPTERS_REQUIRED", prefix + ".chapters", "chapters must be an array.")
            chapters = []
        chapter_ids: set[str] = set()
        memberships: set[str] = set()
        for number, chapter in enumerate(chapters):
            path = f"{prefix}.chapters[{number}]"
            if not isinstance(chapter, dict):
                block("INVALID_CHAPTER", path, "Chapter must be an object.")
                continue
            identifier = chapter.get("id")
            if not _identifier(identifier):
                block("INVALID_CHAPTER_ID", path + ".id", "Chapter ID must be nonempty and trimmed.")
            elif identifier in chapter_ids:
                block("DUPLICATE_CHAPTER_ID", path + ".id", f"Duplicate chapter ID {identifier!r}.")
            else:
                chapter_ids.add(identifier)
            question_ids = chapter.get("questionIds")
            if not isinstance(question_ids, list):
                block("INVALID_CHAPTER_QUESTIONS", path + ".questionIds", "questionIds must be an array.")
                continue
            for position, question_id in enumerate(question_ids):
                ref_path = f"{path}.questionIds[{position}]"
                if not _identifier(question_id) or question_id not in index:
                    block("UNKNOWN_CHAPTER_QUESTION", ref_path, "Chapter refers to an unknown question.")
                elif question_id in memberships:
                    block("DUPLICATE_CHAPTER_QUESTION", ref_path, "Question is listed in more than one chapter position.")
                else:
                    memberships.add(question_id)
                    if "chapterId" in index[question_id] and index[question_id]["chapterId"] != identifier:
                        block("CHAPTER_ID_MISMATCH", ref_path, "Question chapterId does not match its chapter membership.")
        for missing in sorted(set(index) - memberships):
            block("UNASSIGNED_QUESTION", prefix + ".chapters", f"Question {missing!r} has no chapter.")
        return index

    old_questions = course_index(old, "old")
    new_questions = course_index(new, "new")
    if old.get("id") != new.get("id"):
        block("COURSE_ID_CHANGED", "new.id", "A migration must keep the same course ID.")
    if _canonical(old) != _canonical(new) and old.get("version") == new.get("version"):
        block("COURSE_VERSION_NOT_INCREASED", "new.version", "Changed course content requires a different version identifier.")

    if id_map is None:
        entries = []
    elif isinstance(id_map, dict):
        entries = [{"from": key, "to": value} for key, value in id_map.items()]
    elif isinstance(id_map, list):
        entries = id_map
    else:
        raise InputError("id-map must be an object or an array of {from, to} records")
    explicit: dict[str, str] = {}
    seen_sources: set[str] = set()
    for number, entry in enumerate(entries):
        path = f"idMap[{number}]"
        if not isinstance(entry, dict) or set(entry) != {"from", "to"}:
            block("INVALID_MAPPING", path, "Mapping requires exactly 'from' and 'to'.")
            continue
        source, target = entry["from"], entry["to"]
        if not _identifier(source) or not _identifier(target):
            block("INVALID_MAPPING_ID", path, "Mapping IDs must be nonempty trimmed strings.")
            continue
        if source in seen_sources:
            block("DUPLICATE_MAPPING_SOURCE", path, f"Source {source!r} appears more than once.")
            continue
        seen_sources.add(source)
        if source not in old_questions:
            block("UNKNOWN_MAPPING_SOURCE", path + ".from", f"Unknown old question {source!r}.")
            continue
        if target not in new_questions:
            block("UNKNOWN_MAPPING_TARGET", path + ".to", f"Unknown new question {target!r}.")
            continue
        explicit[source] = target
    resolved = {identifier: explicit.get(identifier, identifier)
                for identifier in old_questions
                if identifier in explicit or identifier in new_questions}
    if (any(source != target for source, target in resolved.items()) and
            old.get("version") == new.get("version") and
            not any(reason["code"] == "COURSE_VERSION_NOT_INCREASED" for reason in reasons)):
        block("COURSE_VERSION_NOT_INCREASED", "new.version", "A question ID remapping requires a different course version identifier.")
    targets: dict[str, str] = {}
    for source, target in resolved.items():
        if target in targets:
            block("MANY_TO_ONE_MAPPING", "idMap", f"{targets[target]!r} and {source!r} both resolve to {target!r}.")
        else:
            targets[target] = source

    references: dict[str, list[str]] = {}
    retained_attempt_ids: list[str] = []
    if progress is not None:
        if progress.get("schemaVersion") != "1.0":
            block("PROGRESS_SCHEMA_VERSION", "progress.schemaVersion", "Expected schemaVersion '1.0'.")
        if progress.get("courseId") != old.get("id"):
            block("PROGRESS_COURSE_MISMATCH", "progress.courseId", "Progress must belong to the old course ID.")
        if progress.get("courseVersion") != old.get("version"):
            block("PROGRESS_VERSION_MISMATCH", "progress.courseVersion", "Supply the exact old course version used by this progress export.")
        learner_ids: set[str] = set()
        learners = progress.get("learners")
        if not isinstance(learners, list):
            block("INVALID_LEARNERS", "progress.learners", "learners must be an array.")
            learners = []
        for number, learner in enumerate(learners):
            path = f"progress.learners[{number}]"
            identifier = learner.get("id") if isinstance(learner, dict) else None
            if not _identifier(identifier):
                block("INVALID_LEARNER_ID", path, "Learner requires a nonempty trimmed ID.")
            elif identifier in learner_ids:
                block("DUPLICATE_LEARNER_ID", path, f"Duplicate learner ID {identifier!r}.")
            else:
                learner_ids.add(identifier)

        def validate_reference(record: dict[str, Any], path: str) -> dict[str, Any] | None:
            learner_id, question_id = record.get("learnerId"), record.get("questionId")
            if not _identifier(learner_id) or learner_id not in learner_ids:
                block("UNKNOWN_LEARNER", path + ".learnerId", "Record refers to an unknown learner.")
            if not _identifier(question_id) or question_id not in old_questions:
                block("UNKNOWN_PROGRESS_QUESTION", path + ".questionId", "Record refers to a question absent from the old course.")
                return None
            references.setdefault(question_id, []).append(path)
            return old_questions[question_id]

        attempts = progress.get("attempts")
        if not isinstance(attempts, list):
            block("INVALID_ATTEMPTS", "progress.attempts", "attempts must be an array.")
            attempts = []
        attempt_ids: set[str] = set()
        for number, attempt in enumerate(attempts):
            path = f"progress.attempts[{number}]"
            if not isinstance(attempt, dict):
                block("INVALID_ATTEMPT", path, "Attempt must be an object.")
                continue
            identifier = attempt.get("id")
            if not _identifier(identifier):
                block("INVALID_ATTEMPT_ID", path + ".id", "Attempt requires a nonempty trimmed ID.")
            elif identifier in attempt_ids:
                block("DUPLICATE_ATTEMPT_ID", path + ".id", f"Duplicate attempt ID {identifier!r}.")
            else:
                attempt_ids.add(identifier)
                retained_attempt_ids.append(identifier)
            question = validate_reference(attempt, path)
            revision = attempt.get("questionRevision")
            if not _revision(revision):
                block("INVALID_ATTEMPT_REVISION", path + ".questionRevision", "Attempt revision must be an integer of at least 1.")
            elif question and _revision(question.get("revision")) and revision > question["revision"]:
                block("FUTURE_ATTEMPT_REVISION", path + ".questionRevision", "Attempt revision exceeds the supplied old question revision.")
            if "answer" not in attempt:
                block("MISSING_ATTEMPT_ANSWER", path + ".answer", "Preserved attempt must contain its original answer.")
            if "correct" not in attempt or (attempt["correct"] is not None and not isinstance(attempt["correct"], bool)):
                block("INVALID_ATTEMPT_CORRECT", path + ".correct", "correct must be a boolean or null for an ungraded attempt.")
            status = attempt.get("status")
            if status not in ("graded", "provisional", "pending"):
                block("INVALID_ATTEMPT_STATUS", path + ".status", "Attempt status must be graded, provisional, or pending.")
            elif (status == "pending" and attempt.get("correct") is not None) or (
                    status != "pending" and not isinstance(attempt.get("correct"), bool)):
                block("ATTEMPT_STATUS_CONFLICT", path + ".correct", "Pending attempts require null correctness; graded/provisional attempts require boolean correctness.")
            if not isinstance(attempt.get("countsTowardMastery"), bool) or (
                    status in ("graded", "provisional", "pending") and
                    attempt["countsTowardMastery"] != (status == "graded")):
                block("INVALID_MASTERY_FLAG", path + ".countsTowardMastery", "countsTowardMastery must be true only for graded attempts, and false for provisional/pending attempts.")
            if not _timestamp(attempt.get("at")):
                block("INVALID_ATTEMPT_TIME", path + ".at", "Use an ISO timestamp with seconds and an explicit timezone.")
            if attempt.get("mode") not in ("practice", "review", "mock"):
                block("INVALID_ATTEMPT_MODE", path + ".mode", "Attempt mode must be practice, review, or mock.")
        bookmarks = progress.get("bookmarks")
        if not isinstance(bookmarks, list):
            block("INVALID_BOOKMARKS", "progress.bookmarks", "bookmarks must be an array.")
            bookmarks = []
        bookmark_pairs: set[tuple[str, str]] = set()
        for number, bookmark in enumerate(bookmarks):
            path = f"progress.bookmarks[{number}]"
            if not isinstance(bookmark, dict):
                block("INVALID_BOOKMARK", path, "Bookmark must be an object.")
                continue
            validate_reference(bookmark, path)
            pair = (bookmark.get("learnerId"), bookmark.get("questionId"))
            if all(_identifier(value) for value in pair):
                if pair in bookmark_pairs:
                    block("DUPLICATE_BOOKMARK", path, "Duplicate learner/question bookmark.")
                bookmark_pairs.add(pair)

    changes: list[dict[str, Any]] = []
    for identifier, previous in old_questions.items():
        target = resolved.get(identifier)
        if target is None:
            changes.append({"kind": "removed", "oldQuestionId": identifier,
                            "newQuestionId": None, "referencedBy": references.get(identifier, [])})
            if references.get(identifier):
                block("REFERENCED_QUESTION_REMOVED", "new.questions", f"Deleted question {identifier!r} is referenced by saved attempts or bookmarks; provide a valid one-to-one mapping.")
            continue
        current = new_questions[target]
        fields = sorted(field for field in set(previous) | set(current)
                        if field not in {"id", "revision"} and
                        (field not in previous or field not in current or
                         _canonical(previous[field]) != _canonical(current[field])))
        before, after = previous.get("revision"), current.get("revision")
        if _revision(before) and _revision(after):
            if after < before:
                block("REVISION_DECREASED", "new.questions." + target, "Question revisions cannot decrease.")
            if fields and after <= before:
                block("SEMANTIC_CHANGE_WITHOUT_REVISION", "new.questions." + target, "Question content changed without increasing revision: " + ", ".join(fields))
        if fields or identifier != target or before != after:
            changes.append({"kind": "changed", "oldQuestionId": identifier,
                            "newQuestionId": target, "renamed": identifier != target,
                            "semanticChanged": bool(fields), "changedFields": fields,
                            "fromRevision": before, "toRevision": after,
                            "referencedBy": references.get(identifier, []),
                            "existingAttempts": "preserve unchanged; never regrade"})
    for identifier in new_questions:
        if identifier not in targets:
            changes.append({"kind": "added", "oldQuestionId": None, "newQuestionId": identifier})

    return {
        "schemaVersion": "1.0", "dryRun": True,
        "status": "blocked" if reasons else "ready",
        "courseId": old.get("id"), "fromVersion": old.get("version"), "toVersion": new.get("version"),
        "progressProvided": progress is not None,
        "scope": "Supplied course snapshots and supplied progress export only; unprovided records are not certified.",
        "mappings": [{"from": source, "to": target, "fromVersion": old.get("version"),
                      "toVersion": new.get("version"), "kind": "identity" if source == target else "rename"}
                     for source, target in resolved.items()],
        "changes": changes, "retainedAttemptIds": retained_attempt_ids,
        "blockedReasons": reasons,
        "historyPolicy": {
            "mode": "append-only", "rewriteExistingAttempts": False,
            "regradeExistingAttempts": False,
            "preserveOriginalAttemptFields": "all fields, including IDs, answers, scores, revisions, mode, and timestamps",
            "questionReferenceResolution": "Use the versioned mapping; never overwrite original questionId or questionRevision.",
            "archivalRequirement": "Retain the old course snapshot and available older snapshots so past answers can be interpreted.",
            "changedQuestionProgress": "Keep earlier attempts visible as history; do not count old revisions as mastery of a revised question.",
            "newAttempts": "Append new attempt IDs using the current course version and question revision.",
            "unprovidedProgress": "If progress was omitted, validate each saved export before applying any migration."
        },
        "writesPerformed": [],
    }


def _write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                         prefix=".migration-report-", suffix=".tmp", delete=False) as handle:
            temporary = handle.name
            json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, output)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("old_course", type=Path)
    parser.add_argument("new_course", type=Path)
    parser.add_argument("--progress", type=Path)
    parser.add_argument("--id-map", type=Path)
    parser.add_argument("--output", type=Path, help="Report only; may not overwrite any input file")
    args = parser.parse_args(argv)
    try:
        inputs = [path for path in (args.old_course, args.new_course, args.progress, args.id_map) if path]
        if args.output:
            for path in inputs:
                if args.output.resolve() == path.resolve() or (
                    args.output.exists() and path.exists() and args.output.samefile(path)
                ):
                    raise InputError("The report output must not overwrite an input file")
        report = build_plan(load_json(args.old_course), load_json(args.new_course),
                            load_json(args.progress) if args.progress else None,
                            load_json(args.id_map) if args.id_map else None)
        if args.output:
            _write_report(report, args.output)
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return 1 if report["status"] == "blocked" else 0
    except (InputError, OSError, ValueError, TypeError, RecursionError) as exc:
        print(f"Input/tool error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
