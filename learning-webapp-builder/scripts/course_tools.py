#!/usr/bin/env python3
"""Validate educational course/progress data and grade six objective formats.

Python 3.9+; standard library only. No data is modified. Numeric comparison uses
Decimal, with abs(error) <= max(absoluteTolerance, relativeTolerance*abs(expected)).
"""
import argparse
import json
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

TYPES = {'single_choice', 'multiple_choice', 'numeric', 'cloze_select', 'ordering', 'matching'}
DECIMAL = re.compile(r'^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$')


def parse_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite JSON value: ' + value)))


def read_json(path):
    return parse_json(Path(path).read_text(encoding='utf-8-sig'))


def decimal_value(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError('A finite number or decimal string is required')
    raw = str(value).strip()
    if len(str(value)) > 200 or not DECIMAL.fullmatch(raw):
        raise ValueError('Use a decimal number without units or separators')
    try:
        number = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError('Invalid decimal number') from exc
    if not number.is_finite() or abs(number.adjusted()) > 10000:
        raise ValueError('Number must be finite and exponent must be within supported bounds')
    return number


def text_value(value):
    return isinstance(value, str) and bool(value.strip())


def integer(value, minimum=1):
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _string_list(value, path, errors, nonempty=False):
    if not isinstance(value, list) or (nonempty and not value) or any(not text_value(x) for x in value):
        errors.append(path + ': expected ' + ('nonempty ' if nonempty else '') + 'array of nonempty strings')
        return False
    return True


def _options(value, path, errors, minimum=2, reasons=True):
    if not isinstance(value, list) or len(value) < minimum:
        errors.append(path + ': expected at least ' + str(minimum) + ' options')
        return []
    ids = []
    for index, option in enumerate(value):
        location = path + '[' + str(index) + ']'
        if not isinstance(option, dict):
            errors.append(location + ': expected object')
            continue
        for field in (('id', 'text', 'explanation') if reasons else ('id', 'text')):
            if not text_value(option.get(field)):
                errors.append(location + '.' + field + ': nonempty string required')
        if text_value(option.get('id')):
            if option['id'] in ids:
                errors.append(path + ': duplicate option id ' + option['id'])
            ids.append(option['id'])
    return ids


def answer_errors(question, answer):
    """Validate response shape; never interpret arbitrary text as learner code."""
    kind = question.get('type')
    raw_options = question.get('options', [])
    ids = [x.get('id') for x in raw_options if isinstance(x, dict)] if isinstance(raw_options, list) else []
    if kind == 'single_choice':
        return [] if isinstance(answer, str) and answer in ids else ['Choose one valid option ID']
    if kind in ('multiple_choice', 'ordering'):
        if not isinstance(answer, list) or not answer or any(not isinstance(x, str) for x in answer):
            return ['Submit a nonempty array of option IDs']
        if len(set(answer)) != len(answer) or any(x not in ids for x in answer):
            return ['Option IDs must be unique and valid']
        if kind == 'ordering' and set(answer) != set(ids):
            return ['Ordering must include every option exactly once']
        return []
    if kind == 'numeric':
        try:
            decimal_value(answer)
            return []
        except ValueError as exc:
            return [str(exc)]
    if kind == 'cloze_select':
        slots = question.get('slots', [])
        if not isinstance(slots, list) or not slots or any(not isinstance(s, dict) or not isinstance(s.get('options'), list) for s in slots):
            return ['Question has invalid slot definitions']
        slot_ids = [s.get('id') for s in slots if isinstance(s, dict)]
        if not isinstance(answer, dict) or set(answer) != set(slot_ids):
            return ['Submit exactly one selection for each slot']
        for slot in slots:
            valid = [x.get('id') for x in slot.get('options', []) if isinstance(x, dict)]
            if not isinstance(answer.get(slot['id']), str) or answer[slot['id']] not in valid:
                return ['Every slot must contain a valid option ID']
        return []
    if kind == 'matching':
        items = question.get('items', [])
        if not isinstance(items, list) or not items:
            return ['Question has invalid matching items']
        item_ids = [x.get('id') for x in items if isinstance(x, dict)]
        if not isinstance(answer, dict) or set(answer) != set(item_ids):
            return ['Submit exactly one match for each item']
        if any(not isinstance(x, str) for x in answer.values()) or set(answer.values()) != set(ids) or len(set(answer.values())) != len(answer):
            return ['Matching must use every right-side option exactly once']
        return []
    return ['Unsupported question type']


def validate_course(course):
    errors, warnings = [], []
    if not isinstance(course, dict):
        return {'valid': False, 'errors': ['course: expected object'], 'warnings': []}
    if course.get('schemaVersion') != '1.0':
        errors.append('schemaVersion must be 1.0')
    for key in ('id', 'version', 'title', 'audience'):
        if not text_value(course.get(key)):
            errors.append(key + ': nonempty string required')
    _string_list(course.get('prerequisites'), 'prerequisites', errors)
    _string_list(course.get('goals'), 'goals', errors, True)
    if 'estimatedMinutes' in course and not integer(course['estimatedMinutes']):
        errors.append('estimatedMinutes must be a positive integer')
    questions = course.get('questions')
    if not isinstance(questions, list) or not questions:
        errors.append('questions: nonempty array required')
        questions = []
    by_id = {}
    for index, question in enumerate(questions):
        p = 'questions[' + str(index) + ']'
        if not isinstance(question, dict):
            errors.append(p + ': expected object')
            continue
        for key in ('id', 'prompt', 'chapterId'):
            if not text_value(question.get(key)):
                errors.append(p + '.' + key + ': nonempty string required')
        qid = question.get('id')
        if text_value(qid):
            if qid in by_id:
                errors.append(p + ': duplicate question id ' + qid)
            by_id[qid] = question
        if not integer(question.get('revision')):
            errors.append(p + '.revision: positive integer required')
        difficulty = question.get('difficulty')
        if not integer(difficulty) or difficulty > 10:
            errors.append(p + '.difficulty: integer 1..10 required')
        kind = question.get('type')
        if not isinstance(kind, str) or kind not in TYPES:
            errors.append(p + '.type: unsupported objective format')
            continue
        explanation = question.get('explanation')
        if not isinstance(explanation, dict) or any(not text_value(explanation.get(k)) for k in ('summary', 'correctReason')):
            errors.append(p + '.explanation: summary and correctReason required')
        verification = question.get('verification')
        if not isinstance(verification, dict) or verification.get('status') not in ('verified', 'unverified'):
            errors.append(p + '.verification: verified or unverified status required')
            verification = {}
        if 'reason' in verification and not text_value(verification['reason']):
            errors.append(p + '.verification.reason: nonempty string required when present')
        evidence = verification.get('evidence')
        _string_list(evidence, p + '.verification.evidence', errors, verification.get('status') == 'verified')
        if verification.get('status') == 'unverified':
            if not text_value(verification.get('reason')):
                errors.append(p + '.verification.reason: required for unverified questions')
            warnings.append(p + ': unverified; exclude from confirmed mastery and confirmed mock scores')
        elif verification.get('status') == 'verified' and 'answer' not in question:
            errors.append(p + '.answer: required for verified questions')
        if 'hint' in question:
            hint = question['hint']
            if not isinstance(hint, dict) or any(not text_value(hint.get(k)) for k in ('text', 'rationale')) or hint.get('trigger') != 'on_request':
                errors.append(p + '.hint: text, scaffolding rationale and on_request trigger required')
        if 'options' in question or kind in ('single_choice', 'multiple_choice', 'ordering', 'matching'):
            _options(question.get('options'), p + '.options', errors)
        if 'slots' in question or kind == 'cloze_select':
            slots = question.get('slots')
            if not isinstance(slots, list) or not slots:
                errors.append(p + '.slots: nonempty array required')
            else:
                seen = set()
                for slot in slots:
                    if not isinstance(slot, dict) or not text_value(slot.get('id')) or not text_value(slot.get('label')):
                        errors.append(p + '.slots: every slot needs id and label')
                        continue
                    if slot['id'] in seen:
                        errors.append(p + '.slots: duplicate slot id')
                    seen.add(slot['id'])
                    _options(slot.get('options'), p + '.slots.' + slot['id'] + '.options', errors)
        if 'items' in question or kind == 'matching':
            left_ids = _options(question.get('items'), p + '.items', errors, reasons=False)
            if kind == 'matching' and len(left_ids) != len(question['options'] if isinstance(question.get('options'), list) else []):
                errors.append(p + ': matching needs equal counts of items and options')
        if kind == 'numeric':
            scoring = question.get('scoring', {})
            if not isinstance(scoring, dict):
                errors.append(p + '.scoring: expected object')
            else:
                if set(scoring) - {'absoluteTolerance', 'relativeTolerance'}:
                    errors.append(p + '.scoring: unknown fields; use absoluteTolerance and relativeTolerance only')
                for tolerance in ('absoluteTolerance', 'relativeTolerance'):
                    try:
                        if decimal_value(scoring.get(tolerance, '0')) < 0:
                            raise ValueError('Tolerance cannot be negative')
                    except ValueError as exc:
                        errors.append(p + '.scoring.' + tolerance + ': ' + str(exc))
        elif 'scoring' in question:
            errors.append(p + '.scoring: only numeric tolerances are supported; other formats use exact all-or-nothing grading')
        if 'answer' in question:
            try:
                errors.extend(p + '.answer: ' + error for error in answer_errors(question, question['answer']))
            except (TypeError, KeyError, AttributeError):
                errors.append(p + '.answer: cannot validate until option structure is fixed')
    chapters = course.get('chapters')
    if not isinstance(chapters, list) or not chapters:
        errors.append('chapters: nonempty array required')
        chapters = []
    seen_chapters, assigned, path = set(), set(), []
    for chapter in chapters:
        if not isinstance(chapter, dict) or not text_value(chapter.get('id')) or not text_value(chapter.get('title')):
            errors.append('chapters: each chapter requires id and title')
            continue
        cid = chapter['id']
        if 'lesson' in chapter and not text_value(chapter['lesson']):
            errors.append('chapters.' + cid + '.lesson: nonempty string required when present')
        if 'references' in chapter:
            _string_list(chapter['references'], 'chapters.' + cid + '.references', errors)
        if cid in seen_chapters:
            errors.append('chapters: duplicate chapter id ' + cid)
        seen_chapters.add(cid)
        qids = chapter.get('questionIds')
        if not _string_list(qids, 'chapters.' + cid + '.questionIds', errors, True):
            continue
        for qid in qids:
            if qid in assigned:
                errors.append('chapters: duplicate question assignment ' + qid)
            assigned.add(qid)
            if qid not in by_id:
                errors.append('chapters: unknown question ' + qid)
            else:
                if by_id[qid].get('chapterId') != cid:
                    errors.append('questions.' + qid + '.chapterId disagrees with chapter assignment')
                path.append(by_id[qid])
    for qid in set(by_id) - assigned:
        errors.append('questions.' + qid + ': not assigned to a chapter')
    for before, after in zip(path, path[1:]):
        a, b = before.get('difficulty'), after.get('difficulty')
        if integer(a) and integer(b) and b - a > 2:
            warnings.append('Difficulty jump ' + before['id'] + ' → ' + after['id'] + ': add a bridge or justify the sequence')
    return {'valid': not errors, 'errors': errors, 'warnings': warnings, 'questionCount': len(questions)}


def _timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})', value):
        return False
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo is not None
    except ValueError:
        return False


def validate_progress(progress, course):
    errors, warnings = [], []
    if not isinstance(progress, dict):
        return {'valid': False, 'errors': ['progress: expected object'], 'warnings': []}
    if progress.get('schemaVersion') != '1.0':
        errors.append('progress.schemaVersion must be 1.0')
    if progress.get('courseId') != course.get('id'):
        errors.append('progress.courseId does not match course')
    if not text_value(progress.get('courseVersion')):
        errors.append('progress.courseVersion required')
    elif progress['courseVersion'] != course.get('version'):
        warnings.append('Progress is from another course version; run migration preflight before importing')
    learners = progress.get('learners')
    learner_ids = set()
    if not isinstance(learners, list) or not learners:
        errors.append('progress.learners: nonempty array required')
        learners = []
    for learner in learners:
        if not isinstance(learner, dict) or not text_value(learner.get('id')):
            errors.append('progress.learners: every learner needs an id')
        elif learner['id'] in learner_ids:
            errors.append('progress.learners: duplicate learner id')
        else:
            learner_ids.add(learner['id'])
        if isinstance(learner, dict) and 'displayName' in learner and not text_value(learner['displayName']):
            errors.append('progress.learners.displayName: nonempty string required when present')
    by_id = {q['id']: q for q in course.get('questions', []) if isinstance(q, dict) and text_value(q.get('id'))}
    seen_attempts = set()
    attempts = progress.get('attempts')
    if not isinstance(attempts, list):
        errors.append('progress.attempts: array required')
        attempts = []
    for index, attempt in enumerate(attempts):
        p = 'progress.attempts[' + str(index) + ']'
        if not isinstance(attempt, dict):
            errors.append(p + ': expected object')
            continue
        aid = attempt.get('id')
        if not text_value(aid):
            errors.append(p + '.id required')
        elif aid in seen_attempts:
            errors.append(p + ': duplicate attempt ID; do not import twice')
        else:
            seen_attempts.add(aid)
        if not isinstance(attempt.get('learnerId'), str) or attempt['learnerId'] not in learner_ids:
            errors.append(p + ': unknown learner')
        qid = attempt.get('questionId')
        question = by_id.get(qid) if isinstance(qid, str) else None
        if question is None:
            errors.append(p + ': unknown question')
        revision = attempt.get('questionRevision')
        if not integer(revision):
            errors.append(p + '.questionRevision: positive integer required')
        elif question and integer(question.get('revision')):
            if revision > question['revision']:
                errors.append(p + ': attempt refers to a future question revision')
            elif revision < question['revision']:
                warnings.append(p + ': historical revision retained; do not regrade with the current answer')
            elif 'answer' in attempt:
                errors.extend(p + '.answer: ' + x for x in answer_errors(question, attempt['answer']))
        if 'answer' not in attempt:
            errors.append(p + '.answer required')
        if 'correct' not in attempt or (attempt['correct'] is not None and not isinstance(attempt['correct'], bool)):
            errors.append(p + '.correct must be boolean or null')
        if attempt.get('status') not in ('graded', 'provisional', 'pending'):
            errors.append(p + '.status must be graded, provisional or pending')
        if not isinstance(attempt.get('countsTowardMastery'), bool):
            errors.append(p + '.countsTowardMastery: boolean required')
        status = attempt.get('status')
        if status == 'pending' and attempt.get('correct') is not None:
            errors.append(p + ': pending answers cannot have a correctness judgment')
        if status in ('graded', 'provisional') and not isinstance(attempt.get('correct'), bool):
            errors.append(p + ': graded and provisional answers require boolean correctness')
        if status in ('pending', 'provisional') and attempt.get('countsTowardMastery') is not False:
            errors.append(p + ': unverified attempts must not count toward confirmed mastery')
        if status == 'graded' and attempt.get('countsTowardMastery') is not True:
            errors.append(p + ': graded verified attempts must count toward confirmed mastery')
        if question and revision == question.get('revision'):
            expected_status = 'graded' if question.get('verification', {}).get('status') == 'verified' else ('provisional' if 'answer' in question else 'pending')
            if status != expected_status:
                errors.append(p + ': grading status disagrees with the question verification state')
            if 'answer' in attempt and not answer_errors(question, attempt['answer']):
                reference = grade_question(question, attempt['answer'])
                if attempt.get('correct') is not reference['correct']:
                    errors.append(p + ': stored correctness disagrees with reference grading for the current revision')
        if attempt.get('mode') not in ('practice', 'review', 'mock'):
            errors.append(p + '.mode must be practice, review or mock')
        if not _timestamp(attempt.get('at')):
            errors.append(p + '.at: ISO 8601 timestamp with seconds and timezone required')
    bookmarks = progress.get('bookmarks')
    if not isinstance(bookmarks, list):
        errors.append('progress.bookmarks: array required')
        bookmarks = []
    seen = set()
    for bookmark in bookmarks:
        if not isinstance(bookmark, dict) or not isinstance(bookmark.get('learnerId'), str) or not isinstance(bookmark.get('questionId'), str):
            errors.append('progress.bookmarks: learnerId and questionId strings required')
            continue
        key = (bookmark['learnerId'], bookmark['questionId'])
        if key in seen:
            errors.append('progress.bookmarks: duplicate bookmark')
        seen.add(key)
        if key[0] not in learner_ids or key[1] not in by_id:
            errors.append('progress.bookmarks: unknown learner or question')
    return {'valid': not errors, 'errors': errors, 'warnings': warnings}


def grade_question(question, answer):
    """Grade a structurally validated question. Return invalid for malformed responses."""
    result = {'questionId': question.get('id'), 'questionRevision': question.get('revision'),
              'status': 'invalid', 'correct': None, 'countsTowardMastery': False,
              'feedback': None, 'errors': answer_errors(question, answer)}
    if result['errors']:
        return result
    verified = question.get('verification', {}).get('status') == 'verified'
    if 'answer' not in question:
        result.update(status='pending', feedback={'summary': '正答が未検証のため採点を保留しています。', 'correctReason': '回答は記録できますが、確定成績には含めません。'})
        return result
    expected = question['answer']
    if question['type'] == 'numeric':
        actual, target = decimal_value(answer), decimal_value(expected)
        scoring = question.get('scoring', {})
        with localcontext() as context:
            context.prec = 20250  # Exact subtraction across the bounded exponent range.
            tolerance = max(decimal_value(scoring.get('absoluteTolerance', '0')),
                            decimal_value(scoring.get('relativeTolerance', '0')) * abs(target))
            correct = abs(actual - target) <= tolerance
    elif question['type'] == 'multiple_choice':
        correct = set(answer) == set(expected)
    else:
        correct = answer == expected
    result.update(status='graded' if verified else 'provisional', correct=correct,
                  countsTowardMastery=verified, feedback=question['explanation'], expectedAnswer=expected)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    validate = commands.add_parser('validate', help='Check course and optional saved progress')
    validate.add_argument('course')
    validate.add_argument('--progress')
    validate.add_argument('--json', action='store_true')
    grade = commands.add_parser('grade', help='Grade one JSON-formatted learner response')
    grade.add_argument('course')
    grade.add_argument('question_id')
    grade.add_argument('--answer-json', required=True)
    grade.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        course = read_json(args.course)
        report = validate_course(course)
        if args.command == 'validate':
            if args.progress and report['valid']:
                report['progress'] = validate_progress(read_json(args.progress), course)
                report['valid'] = report['valid'] and report['progress']['valid']
            exit_code = 0 if report['valid'] else 1
        elif not report['valid']:
            exit_code = 1
        else:
            question = next((q for q in course['questions'] if q['id'] == args.question_id), None)
            if question is None:
                raise ValueError('Unknown question ID: ' + args.question_id)
            answer = parse_json(args.answer_json)
            report = grade_question(question, answer)
            exit_code = 2 if report['status'] == 'invalid' else 0
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            if args.command == 'validate':
                print('PASS' if report['valid'] else 'FAIL')
                for key in ('errors', 'warnings'):
                    for message in report.get(key, []):
                        print(key.upper() + ': ' + message)
                for key in ('errors', 'warnings'):
                    for message in report.get('progress', {}).get(key, []):
                        print('PROGRESS ' + key.upper() + ': ' + message)
            else:
                print(json.dumps(report, ensure_ascii=False, indent=2))
        return exit_code
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
