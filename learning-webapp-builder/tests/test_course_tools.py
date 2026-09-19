"""Contract tests: deterministic grades, malformed data and historical attempts."""
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('course_tools', ROOT / 'scripts/course_tools.py')
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.course = tools.read_json(ROOT / 'examples/course.json')
        self.progress = tools.read_json(ROOT / 'examples/progress.json')
        self.q = {q['id']: q for q in self.course['questions']}

    def test_examples_valid(self):
        report = tools.validate_course(self.course)
        self.assertTrue(report['valid'], report)
        self.assertEqual(2, len(report['warnings']))
        self.assertTrue(tools.validate_progress(self.progress, self.course)['valid'])

    def test_correct_all_six_formats(self):
        for q in self.course['questions'][:6]:
            with self.subTest(q=q['id']):
                result = tools.grade_question(q, q['answer'])
                self.assertEqual('graded', result['status'])
                self.assertIs(True, result['correct'])
                self.assertIs(True, result['countsTowardMastery'])
                self.assertTrue(result['feedback']['correctReason'])

    def test_wrong_valid_all_six_formats(self):
        answers = {'q-single':'opt-a', 'q-multiple':['n-2'], 'q-numeric':'359',
                   'q-cloze':{'operation':'add'}, 'q-order':['whole','half','third'],
                   'q-match':{'triangle':'four','quadrilateral':'three'}}
        for qid, answer in answers.items():
            with self.subTest(q=qid):
                result = tools.grade_question(self.q[qid], answer)
                self.assertEqual('graded', result['status'])
                self.assertIs(False, result['correct'])

    def test_multiple_choice_order_irrelevant(self):
        self.assertTrue(tools.grade_question(self.q['q-multiple'], ['n-4','n-2'])['correct'])

    def test_multiple_choice_duplicate_or_extra_invalid(self):
        for answer in ([],['n-2','n-2'],['missing'], True, 'n-2', [2]):
            self.assertEqual('invalid', tools.grade_question(self.q['q-multiple'], answer)['status'])

    def test_single_unknown_or_wrong_type_invalid(self):
        for answer in ('', 'missing', ['opt-b'], 2, False, None, {}):
            self.assertEqual('invalid', tools.grade_question(self.q['q-single'], answer)['status'])

    def test_order_requires_complete_permutation(self):
        for answer in (['third','half'], ['third','half','half'], ['third','half','whole','x']):
            self.assertEqual('invalid', tools.grade_question(self.q['q-order'], answer)['status'])

    def test_matching_requires_bijection_and_all_left_items(self):
        for answer in ({'triangle':'three'}, {'triangle':'three','quadrilateral':'three'},
                       {'triangle':'three','quadrilateral':'four','other':'four'},
                       {'triangle':3,'quadrilateral':'four'}):
            self.assertEqual('invalid', tools.grade_question(self.q['q-match'], answer)['status'])

    def test_cloze_requires_all_and_only_slots(self):
        for answer in ({}, {'operation':'unknown'}, {'operation':'multiply','extra':'multiply'}, {'operation':['multiply']}):
            self.assertEqual('invalid', tools.grade_question(self.q['q-cloze'], answer)['status'])

    def test_numeric_equivalent_strings_and_numbers(self):
        for answer in ('360', ' 360.0 ', '3.6e2', '+360', 360, 360.0):
            self.assertTrue(tools.grade_question(self.q['q-numeric'], answer)['correct'])

    def test_numeric_rejects_blank_bool_nan_unicode_and_units(self):
        for answer in ('', ' ', True, False, None, [], {}, 'NaN', 'Infinity', float('inf'), float('nan'),
                       '３６０','360円','3,600','1/3','1e10001'):
            with self.subTest(answer=answer):
                self.assertEqual('invalid', tools.grade_question(self.q['q-numeric'], answer)['status'])

    def test_zero_tolerance_is_exact(self):
        question = self.q['q-numeric']
        question['answer'] = '0.3'
        self.assertTrue(tools.grade_question(question, '0.30')['correct'])
        self.assertFalse(tools.grade_question(question, '0.30000000000000000000000000001')['correct'])

    def test_absolute_tolerance_inclusive_boundary(self):
        question = self.q['q-numeric']
        question['answer'] = '10'
        question['scoring']['absoluteTolerance'] = '0.1'
        for answer in ('9.9','10.1'):
            self.assertTrue(tools.grade_question(question, answer)['correct'])
        for answer in ('9.8999999','10.1000001'):
            self.assertFalse(tools.grade_question(question, answer)['correct'])

    def test_relative_tolerance_negative_and_zero_target(self):
        question = self.q['q-numeric']
        question['answer'] = '-100'
        question['scoring']['relativeTolerance'] = '0.01'
        self.assertTrue(tools.grade_question(question, '-99')['correct'])
        self.assertFalse(tools.grade_question(question, '-98.999')['correct'])
        question['answer'] = '0'
        self.assertFalse(tools.grade_question(question, '0.00001')['correct'])

    def test_provisional_never_counts_as_confirmed(self):
        result = tools.grade_question(self.q['q-provisional'], '20')
        self.assertEqual('provisional', result['status'])
        self.assertTrue(result['correct'])
        self.assertFalse(result['countsTowardMastery'])

    def test_pending_has_no_false_judgment_or_expected_answer(self):
        for answer in ('up','down'):
            result = tools.grade_question(self.q['q-pending'], answer)
            self.assertEqual('pending', result['status'])
            self.assertIsNone(result['correct'])
            self.assertFalse(result['countsTowardMastery'])
            self.assertNotIn('expectedAnswer', result)

    def test_pending_still_validates_response(self):
        self.assertEqual('invalid', tools.grade_question(self.q['q-pending'], 'missing')['status'])

    def test_duplicate_ids_detected(self):
        self.course['questions'].append(copy.deepcopy(self.course['questions'][0]))
        self.assertFalse(tools.validate_course(self.course)['valid'])

    def test_dangling_chapter_and_wrong_assignment_detected(self):
        self.course['chapters'][0]['questionIds'].append('missing')
        self.course['questions'][0]['chapterId'] = 'wrong'
        errors = tools.validate_course(self.course)['errors']
        self.assertTrue(any('unknown question' in x for x in errors))
        self.assertTrue(any('disagrees' in x for x in errors))

    def test_wrong_answer_membership_detected(self):
        self.q['q-single']['answer'] = 'not-an-option'
        self.assertFalse(tools.validate_course(self.course)['valid'])

    def test_duplicate_option_and_slot_ids_detected(self):
        self.q['q-single']['options'].append(copy.deepcopy(self.q['q-single']['options'][0]))
        self.q['q-cloze']['slots'].append(copy.deepcopy(self.q['q-cloze']['slots'][0]))
        self.assertFalse(tools.validate_course(self.course)['valid'])

    def test_option_reason_required_even_wrong_choices(self):
        del self.q['q-single']['options'][0]['explanation']
        self.assertFalse(tools.validate_course(self.course)['valid'])

    def test_verified_requires_answer_and_evidence(self):
        del self.q['q-single']['answer']
        self.q['q-numeric']['verification']['evidence'] = []
        self.assertFalse(tools.validate_course(self.course)['valid'])

    def test_unverified_requires_reason(self):
        del self.q['q-provisional']['verification']['reason']
        self.assertFalse(tools.validate_course(self.course)['valid'])

    def test_negative_tolerance_rejected(self):
        self.q['q-numeric']['scoring']['absoluteTolerance'] = '-0.1'
        self.assertFalse(tools.validate_course(self.course)['valid'])

    def test_unsupported_free_text_rejected(self):
        self.q['q-single']['type'] = 'free_text'
        self.assertFalse(tools.validate_course(self.course)['valid'])

    def test_hint_needs_scaffolding_rationale(self):
        del self.q['q-cloze']['hint']['rationale']
        self.assertFalse(tools.validate_course(self.course)['valid'])

    def test_difficulty_warning_does_not_hard_lock(self):
        self.q['q-multiple']['difficulty'] = 8
        report = tools.validate_course(self.course)
        self.assertTrue(report['valid'])
        self.assertTrue(any('Difficulty jump' in x for x in report['warnings']))

    def test_invalid_field_types_do_not_crash_validation(self):
        candidates = [None, True, 3, [], {}, '']
        for field in ('options','items','slots','scoring','verification','hint','difficulty','revision','type','answer'):
            for value in candidates:
                with self.subTest(field=field,value=value):
                    course = copy.deepcopy(self.course)
                    for question in course['questions']:
                        if field in question or field == 'hint':
                            question[field] = value
                    report = tools.validate_course(course)
                    self.assertIsInstance(report['valid'], bool)

    def test_progress_different_learners_and_duplicate_attempt_ids(self):
        self.progress['learners'].append({'id':'second'})
        record = copy.deepcopy(self.progress['attempts'][0])
        record.update(id='new-attempt',learnerId='second')
        self.progress['attempts'].append(record)
        self.assertTrue(tools.validate_progress(self.progress,self.course)['valid'])
        self.progress['attempts'][-1]['id']='attempt-1'
        self.assertFalse(tools.validate_progress(self.progress,self.course)['valid'])

    def test_progress_rejects_unknown_learner_and_question(self):
        self.progress['attempts'][0].update(learnerId='missing',questionId='missing')
        self.assertFalse(tools.validate_progress(self.progress,self.course)['valid'])

    def test_progress_retains_stale_revision_without_regrading(self):
        before = copy.deepcopy(self.progress)
        self.q['q-single']['revision'] = 2
        self.q['q-single']['answer'] = 'opt-a'
        self.q['q-single']['options'] = [option for option in self.q['q-single']['options'] if option['id'] != 'opt-b']
        self.assertTrue(tools.validate_course(self.course)['valid'])
        report = tools.validate_progress(self.progress,self.course)
        self.assertTrue(report['valid'],report)
        self.assertTrue(any('historical' in x for x in report['warnings']))
        self.assertEqual(before,self.progress)

    def test_progress_current_revision_corrupt_correctness_detected_without_mutation(self):
        self.progress['attempts'][0]['answer'] = 'opt-a'
        before = copy.deepcopy(self.progress)
        report = tools.validate_progress(self.progress,self.course)
        self.assertFalse(report['valid'])
        self.assertTrue(any('stored correctness disagrees' in x for x in report['errors']))
        self.assertEqual(before,self.progress)

    def test_progress_provisional_current_revision_corrupt_correctness_detected(self):
        self.progress['attempts'][1]['answer'] = '19'
        report = tools.validate_progress(self.progress,self.course)
        self.assertFalse(report['valid'])
        self.assertTrue(any('stored correctness disagrees' in x for x in report['errors']))

    def test_progress_future_revision_rejected(self):
        self.progress['attempts'][0]['questionRevision']=2
        self.assertFalse(tools.validate_progress(self.progress,self.course)['valid'])

    def test_progress_no_false_pending_or_provisional_mastery(self):
        for index in (1,2):
            progress = copy.deepcopy(self.progress)
            progress['attempts'][index]['countsTowardMastery'] = True
            self.assertFalse(tools.validate_progress(progress,self.course)['valid'])
        self.progress['attempts'][2]['correct'] = False
        self.assertFalse(tools.validate_progress(self.progress,self.course)['valid'])

    def test_progress_wrong_grading_status_rejected(self):
        self.progress['attempts'][1].update(status='graded',countsTowardMastery=True)
        self.assertFalse(tools.validate_progress(self.progress,self.course)['valid'])

    def test_timestamp_requires_timezone_and_real_calendar_date(self):
        for timestamp in ('2026-01-01T10:00:00','2026-02-30T10:00:00Z','yesterday',True):
            self.progress['attempts'][0]['at']=timestamp
            self.assertFalse(tools.validate_progress(self.progress,self.course)['valid'])

    def test_json_duplicate_keys_and_nonfinite_tokens_rejected(self):
        for raw in ('{"a":1,"a":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.assertRaises(ValueError):
                tools.parse_json(raw)

    def test_cli_validate_and_grade(self):
        command = [sys.executable,str(ROOT/'scripts/course_tools.py')]
        result = subprocess.run(command+['validate',str(ROOT/'examples/course.json'),'--progress',str(ROOT/'examples/progress.json'),'--json'],capture_output=True,text=True)
        self.assertEqual(0,result.returncode,result.stderr)
        self.assertTrue(json.loads(result.stdout)['valid'])
        result = subprocess.run(command+['grade',str(ROOT/'examples/course.json'),'q-single','--answer-json','"opt-b"','--json'],capture_output=True,text=True)
        self.assertEqual(0,result.returncode,result.stderr)
        self.assertTrue(json.loads(result.stdout)['correct'])
        result = subprocess.run(command+['grade',str(ROOT/'examples/course.json'),'q-numeric','--answer-json','true','--json'],capture_output=True,text=True)
        self.assertEqual(2,result.returncode)
        self.assertEqual('invalid',json.loads(result.stdout)['status'])

    def test_optional_known_fields_and_unknown_scoring_keys(self):
        self.q['q-numeric']['scoring']['relTolerance'] = '0.1'
        self.course['chapters'][0]['lesson'] = 12
        self.course['chapters'][0]['references'] = 'not an array'
        report = tools.validate_course(self.course)
        self.assertFalse(report['valid'])
        self.assertTrue(any('unknown fields' in x for x in report['errors']))
        self.assertTrue(any('.lesson:' in x for x in report['errors']))
        self.assertTrue(any('.references:' in x for x in report['errors']))
        self.progress['learners'][0]['displayName'] = False
        self.assertFalse(tools.validate_progress(self.progress,self.course)['valid'])

    def test_decimal_tiny_tolerance_boundary_is_exact(self):
        question = self.q['q-numeric']
        question['answer'] = '0.30000000000000000000000000000'
        question['scoring']['absoluteTolerance'] = '0.00000000000000000000000000001'
        self.assertTrue(tools.grade_question(question, '0.30000000000000000000000000001')['correct'])
        self.assertFalse(tools.grade_question(question, '0.30000000000000000000000000002')['correct'])

    def test_answer_checker_rejects_malformed_option_containers(self):
        for qid, field in [('q-single','options'),('q-cloze','slots'),('q-match','items')]:
            for value in (None, True, 2, {}):
                question = copy.deepcopy(self.q[qid])
                question[field] = value
                self.assertTrue(tools.answer_errors(question, question['answer']))

    def test_cli_bad_file_returns_input_error(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'broken.json'
            target.write_text('{bad json')
            result = subprocess.run([sys.executable,str(ROOT/'scripts/course_tools.py'),'validate',str(target)],capture_output=True,text=True)
            self.assertEqual(2,result.returncode)
            self.assertIn('error',json.loads(result.stderr))


if __name__ == '__main__':
    unittest.main()
