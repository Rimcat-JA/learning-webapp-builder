"""Migration safety regressions; run with unittest discovery (standard library)."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_migration.py"
SPEC = importlib.util.spec_from_file_location("check_migration", SCRIPT)
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


def question(identifier="q1", answer=3):
    return {"id": identifier, "revision": 1, "type": "numeric",
            "chapterId": "c1", "verification": {"status": "verified"},
            "prompt": "1 + 2 は？", "answer": answer,
            "scoring": {"absoluteTolerance": 0}, "explanation": "1 に 2 を足すと 3。"}


def course():
    return {"schemaVersion": "1.0", "id": "arithmetic", "version": "1.0.0",
            "questions": [question(), question("q2", 4)],
            "chapters": [{"id": "c1", "questionIds": ["q1", "q2"]}]}


def progress():
    return {"schemaVersion": "1.0", "courseId": "arithmetic", "courseVersion": "1.0.0",
            "learners": [{"id": "learner-1"}, {"id": "learner-2"}],
            "attempts": [{"id": "a1", "learnerId": "learner-1", "questionId": "q1",
                          "questionRevision": 1, "answer": 3, "correct": True,
                          "status": "graded", "countsTowardMastery": True,
                          "at": "2026-09-19T15:30:00+09:00", "mode": "practice"}],
            "bookmarks": [{"learnerId": "learner-2", "questionId": "q2"}]}


def codes(plan):
    return {reason["code"] for reason in plan["blockedReasons"]}


class MigrationPlanTests(unittest.TestCase):
    def setUp(self):
        self.old = course()
        self.new = copy.deepcopy(self.old)
        self.records = progress()

    def plan(self, mapping=None):
        return migration.build_plan(self.old, self.new, self.records, mapping)

    def test_noop_retains_attempts_and_does_not_mutate_inputs(self):
        original = copy.deepcopy((self.old, self.new, self.records))
        plan = self.plan()
        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["retainedAttemptIds"], ["a1"])
        self.assertEqual(plan["changes"], [])
        self.assertEqual(plan["writesPerformed"], [])
        self.assertEqual((self.old, self.new, self.records), original)

    def test_rename_is_versioned_and_preserves_original_history(self):
        self.new["version"] = "1.1.0"
        self.new["questions"][0]["id"] = "new-q1"
        self.new["chapters"][0]["questionIds"][0] = "new-q1"
        plan = self.plan({"q1": "new-q1"})
        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["mappings"][0]["fromVersion"], "1.0.0")
        self.assertEqual(plan["mappings"][0]["to"], "new-q1")
        self.assertEqual(self.records["attempts"][0]["questionId"], "q1")
        self.assertEqual(plan["retainedAttemptIds"], ["a1"])

    def test_every_question_content_field_requires_revision_increase(self):
        cases = {"answer": 5, "prompt": "2 + 3 は？", "explanation": "計算を修正。",
                 "type": "single_choice", "options": [{"id": "a", "label": "5"}],
                 "scoring": {"absoluteTolerance": 1}, "source": {"url": "https://example.test"}}
        for field, value in cases.items():
            with self.subTest(field=field):
                self.new = copy.deepcopy(self.old)
                self.new["version"] = "1.1.0"
                self.new["questions"][0][field] = value
                plan = self.plan()
                self.assertIn("SEMANTIC_CHANGE_WITHOUT_REVISION", codes(plan))
                self.assertIn(field, plan["changes"][0]["changedFields"])

    def test_revised_answer_does_not_change_previous_score(self):
        self.new["version"] = "2.0.0"
        self.new["questions"][0].update(answer=4, revision=2)
        original = copy.deepcopy(self.records)
        plan = self.plan()
        self.assertEqual(plan["status"], "ready")
        self.assertEqual(self.records, original)
        self.assertFalse(plan["historyPolicy"]["regradeExistingAttempts"])
        self.assertFalse(plan["historyPolicy"]["rewriteExistingAttempts"])
        self.assertTrue(plan["changes"][0]["semanticChanged"])

    def test_boolean_and_integer_answer_are_not_the_same(self):
        self.old["questions"][0]["answer"] = 1
        self.new = copy.deepcopy(self.old)
        self.new["version"] = "1.1.0"
        self.new["questions"][0]["answer"] = True
        self.assertIn("SEMANTIC_CHANGE_WITHOUT_REVISION", codes(self.plan()))

    def test_decreased_revision_is_blocked(self):
        self.old["questions"][0]["revision"] = 3
        self.new["version"] = "1.1.0"
        self.assertIn("REVISION_DECREASED", codes(self.plan()))

    def test_deleting_attempt_or_bookmark_question_is_blocked(self):
        for identifier in ("q1", "q2"):
            with self.subTest(identifier=identifier):
                self.new = copy.deepcopy(self.old)
                self.new["version"] = "1.1.0"
                self.new["questions"] = [q for q in self.new["questions"] if q["id"] != identifier]
                self.new["chapters"][0]["questionIds"].remove(identifier)
                self.assertIn("REFERENCED_QUESTION_REMOVED", codes(self.plan()))

    def test_unreferenced_deletion_is_allowed(self):
        self.records["bookmarks"] = []
        self.new["version"] = "1.1.0"
        self.new["questions"].pop()
        self.new["chapters"][0]["questionIds"].pop()
        plan = self.plan()
        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["changes"][0]["kind"], "removed")

    def test_no_progress_report_does_not_claim_all_history_verified(self):
        plan = migration.build_plan(self.old, self.new)
        self.assertEqual(plan["status"], "ready")
        self.assertFalse(plan["progressProvided"])
        self.assertIn("unprovided records", plan["scope"])
        self.assertEqual(plan["retainedAttemptIds"], [])

    def test_many_to_one_includes_implicit_identity_collision(self):
        plan = self.plan({"q1": "q2"})
        self.assertIn("MANY_TO_ONE_MAPPING", codes(plan))

    def test_many_to_one_explicit_mapping_is_blocked(self):
        plan = self.plan([{"from": "q1", "to": "q2"}, {"from": "q2", "to": "q2"}])
        self.assertIn("MANY_TO_ONE_MAPPING", codes(plan))

    def test_id_swap_requires_new_course_version_even_when_content_is_identical(self):
        self.old["questions"][1]["answer"] = 3
        self.new = copy.deepcopy(self.old)
        plan = self.plan({"q1": "q2", "q2": "q1"})
        self.assertIn("COURSE_VERSION_NOT_INCREASED", codes(plan))
        self.new["version"] = "1.1.0"
        self.assertEqual(self.plan({"q1": "q2", "q2": "q1"})["status"], "ready")

    def test_unknown_mapping_endpoints_and_duplicate_sources(self):
        cases = [({"absent": "q1"}, "UNKNOWN_MAPPING_SOURCE"),
                 ({"q1": "absent"}, "UNKNOWN_MAPPING_TARGET"),
                 ([{"from": "q1", "to": "q1"}, {"from": "q1", "to": "q2"}], "DUPLICATE_MAPPING_SOURCE"),
                 ([{"from": "q1", "to": "q1", "discard": True}], "INVALID_MAPPING"),
                 ({"q1": []}, "INVALID_MAPPING_ID")]
        for mapping, expected in cases:
            with self.subTest(expected=expected):
                self.assertIn(expected, codes(self.plan(mapping)))

    def test_changed_course_version_required_even_for_chapter_title(self):
        self.new["chapters"][0]["title"] = "基礎"
        self.assertIn("COURSE_VERSION_NOT_INCREASED", codes(self.plan()))

    def test_course_and_progress_identity_mismatches(self):
        self.new["id"] = "another-course"
        self.records["courseId"] = "unrelated"
        self.records["courseVersion"] = "0.9.0"
        self.assertTrue({"COURSE_ID_CHANGED", "PROGRESS_COURSE_MISMATCH", "PROGRESS_VERSION_MISMATCH"} <= codes(self.plan()))

    def test_duplicate_question_chapter_learner_attempt_bookmark_ids(self):
        self.new["questions"].append(copy.deepcopy(self.new["questions"][0]))
        self.new["chapters"].append(copy.deepcopy(self.new["chapters"][0]))
        self.records["learners"].append(copy.deepcopy(self.records["learners"][0]))
        self.records["attempts"].append(copy.deepcopy(self.records["attempts"][0]))
        self.records["bookmarks"].append(copy.deepcopy(self.records["bookmarks"][0]))
        self.assertTrue({"DUPLICATE_QUESTION_ID", "DUPLICATE_CHAPTER_ID", "DUPLICATE_CHAPTER_QUESTION",
                         "DUPLICATE_LEARNER_ID", "DUPLICATE_ATTEMPT_ID", "DUPLICATE_BOOKMARK"} <= codes(self.plan()))

    def test_unknown_learner_and_question_are_blocked(self):
        self.records["attempts"][0]["learnerId"] = "missing"
        self.records["attempts"][0]["questionId"] = "missing"
        self.assertTrue({"UNKNOWN_LEARNER", "UNKNOWN_PROGRESS_QUESTION"} <= codes(self.plan()))

    def test_invalid_dates_are_blocked_and_valid_utc_allowed(self):
        for value in ("2026-09-19", "2026-09-19T12:00:00", "2026-02-30T12:00:00Z", "yesterday", 0):
            with self.subTest(value=value):
                self.records["attempts"][0]["at"] = value
                self.assertIn("INVALID_ATTEMPT_TIME", codes(self.plan()))
        for value in ("2026-09-19T12:00:00Z", "2026-09-19T12:00:00.123+09:00"):
            self.records["attempts"][0]["at"] = value
            self.assertEqual(self.plan()["status"], "ready")

    def test_future_attempt_revision_blocked_but_historical_revision_preserved(self):
        self.records["attempts"][0]["questionRevision"] = 2
        self.assertIn("FUTURE_ATTEMPT_REVISION", codes(self.plan()))
        self.old["questions"][0]["revision"] = 3
        self.new = copy.deepcopy(self.old)
        self.assertEqual(self.plan()["status"], "ready")

    def test_ungraded_attempts_are_preserved(self):
        self.records["attempts"][0]["correct"] = None
        self.records["attempts"][0]["status"] = "pending"
        self.records["attempts"][0]["countsTowardMastery"] = False
        self.assertEqual(self.plan()["status"], "ready")

    def test_unverified_question_can_omit_answer_but_verified_question_cannot(self):
        del self.old["questions"][0]["answer"]
        self.old["questions"][0]["verification"]["status"] = "unverified"
        self.new = copy.deepcopy(self.old)
        self.assertEqual(self.plan()["status"], "ready")
        self.old["questions"][0]["verification"]["status"] = "verified"
        self.assertIn("MISSING_QUESTION_FIELD", codes(self.plan()))

    def test_provisional_attempt_cannot_count_toward_mastery(self):
        self.records["attempts"][0]["status"] = "provisional"
        self.assertIn("INVALID_MASTERY_FLAG", codes(self.plan()))
        self.records["attempts"][0]["countsTowardMastery"] = False
        self.assertEqual(self.plan()["status"], "ready")

    def test_pending_attempt_cannot_claim_correctness(self):
        self.records["attempts"][0]["status"] = "pending"
        self.records["attempts"][0]["countsTowardMastery"] = False
        self.assertIn("ATTEMPT_STATUS_CONFLICT", codes(self.plan()))

    def test_question_chapter_id_must_match_membership(self):
        self.old["questions"][0]["chapterId"] = "other"
        self.assertIn("CHAPTER_ID_MISMATCH", codes(self.plan()))

    def test_invalid_revision_bool_and_invalid_record_types_are_blocked(self):
        self.old["questions"][0]["revision"] = True
        self.records["attempts"][0]["questionRevision"] = True
        self.records["attempts"][0]["correct"] = "yes"
        self.records["attempts"][0]["mode"] = ""
        self.assertTrue({"INVALID_REVISION", "INVALID_ATTEMPT_REVISION", "INVALID_ATTEMPT_CORRECT", "INVALID_ATTEMPT_MODE"} <= codes(self.plan()))

    def test_malformed_references_do_not_crash(self):
        self.records["attempts"][0]["learnerId"] = {"oops": 1}
        self.records["attempts"][0]["questionId"] = ["q1"]
        self.records["bookmarks"][0]["questionId"] = {"id": "q2"}
        self.new["chapters"][0]["questionIds"] = [["q1"], "q2"]
        self.assertEqual(self.plan()["status"], "blocked")

    def test_non_objects_and_non_finite_inputs_raise_input_error(self):
        for value in ([], None, "course"):
            with self.subTest(value=value), self.assertRaises(migration.InputError):
                migration.build_plan(value, self.new)
        self.old["questions"][0]["answer"] = float("inf")
        with self.assertRaises(migration.InputError):
            self.plan()


class MigrationCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old = self.root / "old.json"
        self.new = self.root / "new.json"
        self.records = self.root / "progress.json"
        self.output = self.root / "report.json"
        self.old.write_text(json.dumps(course()), encoding="utf-8")
        self.new.write_text(json.dumps(course()), encoding="utf-8")
        self.records.write_text(json.dumps(progress()), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *extra):
        return subprocess.run([sys.executable, str(SCRIPT), str(self.old), str(self.new),
                               "--progress", str(self.records), *map(str, extra)],
                              text=True, capture_output=True, timeout=10)

    def test_ready_report_written_without_touching_inputs(self):
        paths = [self.old, self.new, self.records]
        before = [path.read_bytes() for path in paths]
        result = self.run_cli("--output", self.output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.output.read_text())["status"], "ready")
        self.assertEqual([path.read_bytes() for path in paths], before)

    def test_blocked_report_written_with_exit_one(self):
        changed = course()
        changed["questions"][0]["answer"] = 100
        self.new.write_text(json.dumps(changed), encoding="utf-8")
        result = self.run_cli("--output", self.output)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(self.output.read_text())["status"], "blocked")

    def test_stdout_report_supported(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["retainedAttemptIds"], ["a1"])

    def test_duplicate_json_key_and_nan_are_input_errors(self):
        for value in ('{"id":"first","id":"second"}', '{"answer": NaN}', '{"answer":1e999}', '{invalid'):
            with self.subTest(value=value):
                self.new.write_text(value, encoding="utf-8")
                result = self.run_cli()
                self.assertEqual(result.returncode, 2)
                self.assertIn("Input/tool error", result.stderr)

    def test_report_cannot_overwrite_input(self):
        for output in (self.old, self.new, self.records):
            with self.subTest(output=output):
                before = output.read_bytes()
                result = self.run_cli("--output", output)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(output.read_bytes(), before)

    def test_report_cannot_overwrite_input_via_hardlink_or_symlink(self):
        for link_name, create in (("alias-hard.json", lambda p: p.hardlink_to(self.old)),
                                  ("alias-sym.json", lambda p: p.symlink_to(self.old))):
            alias = self.root / link_name
            try:
                create(alias)
            except (OSError, NotImplementedError):
                continue
            result = self.run_cli("--output", alias)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(self.old.read_text())["id"], "arithmetic")

    def test_duplicate_mapping_key_is_not_silently_overwritten(self):
        mapping = self.root / "map.json"
        mapping.write_text('{"q1":"q1","q1":"q2"}', encoding="utf-8")
        result = self.run_cli("--id-map", mapping)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Duplicate JSON key", result.stderr)


if __name__ == "__main__":
    unittest.main()
