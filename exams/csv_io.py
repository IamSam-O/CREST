import csv
import io

from django.db import transaction

from .models import Exam, InProgressAttempt, Option, Question
from .sanitize import sanitize_html

OPTION_COLUMNS = ['Option 1', 'Option 2', 'Option 3', 'Option 4', 'Option 5', 'Option 6']
HEADER = ['Question Text', 'Question Type', *OPTION_COLUMNS, 'Correct Answer', 'Points', 'Image Link', 'Answer explanation']


class CsvImportError(Exception):
    pass


def _detect_type(raw_type, correct_answer):
    normalized = (raw_type or '').strip().lower()
    if 'checkbox' in normalized or 'multi' in normalized:
        return Question.MULTI
    if sum(1 for s in correct_answer.split(',') if s.strip()) > 1:
        return Question.MULTI
    return Question.SINGLE


def parse_rows(csv_text):
    csv_text = csv_text.lstrip('﻿')
    reader = csv.DictReader(io.StringIO(csv_text))
    records = [row for row in reader if any((v or '').strip() for v in row.values())]

    if not records:
        raise CsvImportError('CSV file has no question rows.')

    required = ['Question Text', 'Question Type', 'Correct Answer']
    header_cols = list(records[0].keys())
    for col in required:
        if col not in header_cols:
            raise CsvImportError(f'CSV is missing required column "{col}".')

    rows = []
    for row in records:
        question_text = (row.get('Question Text') or '').strip()
        if not question_text:
            continue

        correct_answer_raw = (row.get('Correct Answer') or '').strip()
        correct_indexes = set()
        for s in correct_answer_raw.split(','):
            s = s.strip()
            if s.lstrip('-').isdigit():
                correct_indexes.add(int(s))

        question_type = _detect_type(row.get('Question Type'), correct_answer_raw)
        try:
            points = int(row.get('Points') or 0)
        except ValueError:
            points = 0
        points = points if points > 0 else 1
        image_link = (row.get('Image Link') or '').strip() or None
        explanation = (row.get('Answer explanation') or '').strip() or None

        options = []
        for col_idx, col in enumerate(OPTION_COLUMNS):
            text = (row.get(col) or '').strip()
            if not text:
                continue
            options.append({'text': text, 'is_correct': (col_idx + 1) in correct_indexes})

        rows.append({
            'question_text': question_text,
            'type': question_type,
            'points': points,
            'image_link': image_link,
            'explanation': explanation,
            'options': options,
        })

    if not rows:
        raise CsvImportError('No valid question rows found in CSV.')

    return rows


def _insert_questions(exam, rows, sanitize=True):
    for idx, row in enumerate(rows):
        question = Question.objects.create(
            exam=exam,
            question_text=sanitize_html(row['question_text']) if sanitize else row['question_text'],
            question_type=row['type'],
            points=row['points'],
            image_link=row['image_link'],
            explanation=(sanitize_html(row['explanation']) if sanitize else row['explanation']) if row['explanation'] else None,
            sort_order=idx,
        )
        Option.objects.bulk_create([
            Option(
                question=question,
                option_text=sanitize_html(opt['text']) if sanitize else opt['text'],
                is_correct=opt['is_correct'],
                sort_order=opt_idx,
            )
            for opt_idx, opt in enumerate(row['options'])
        ])


@transaction.atomic
def import_csv(csv_text, exam_name, source_filename=None, owner=None, group_ids=None):
    rows = parse_rows(csv_text)
    exam = Exam.objects.create(name=exam_name, source_filename=source_filename, owner=owner)
    if group_ids:
        exam.allowed_groups.set(group_ids)
    _insert_questions(exam, rows)
    return exam.id, len(rows)


@transaction.atomic
def replace_exam_questions(exam, csv_text):
    """Wholesale-replaces an existing exam's questions (CSV re-upload).
    Old questions cascade-delete their options and any historical
    attempt_answers rows; the in-progress attempt for this exam is also
    cleared by the caller since its saved question ids would go stale."""
    rows = parse_rows(csv_text)
    exam.questions.all().delete()
    _insert_questions(exam, rows)
    InProgressAttempt.objects.filter(exam=exam).delete()
    return len(rows)


def export_exam_to_csv(exam):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(HEADER)
    for question in exam.questions.order_by('sort_order').prefetch_related('options'):
        options = list(question.options.order_by('sort_order'))
        correct_indexes = ','.join(str(i + 1) for i, o in enumerate(options) if o.is_correct)
        option_cells = [options[i].option_text if i < len(options) else '' for i in range(len(OPTION_COLUMNS))]
        writer.writerow([
            question.question_text,
            'Checkbox' if question.question_type == Question.MULTI else 'Multiple Choice',
            *option_cells,
            correct_indexes,
            question.points,
            question.image_link or '',
            question.explanation or '',
        ])
    return buf.getvalue()
