import csv
import io

from django.db import transaction

from .models import InProgressInstance, Option, Question, QuestionBank
from .sanitize import sanitize_html

OPTION_COLUMNS = ['Option 1', 'Option 2', 'Option 3', 'Option 4', 'Option 5', 'Option 6']
HEADER = ['Question Text', 'Question Type', 'Category', *OPTION_COLUMNS, 'Correct Answer', 'Points', 'Image Link', 'Answer explanation']


class CsvImportError(Exception):
    pass


def decode_csv_upload(upload):
    raw = upload.read()
    try:
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        return raw.decode('latin-1')


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

        rows.append({
            'question_text': question_text,
            'type': question_type,
            'points': points,
            'image_link': (row.get('Image Link') or '').strip() or None,
            'explanation': (row.get('Answer explanation') or '').strip() or None,
            'category': (row.get('Category') or '').strip(),
            'options': [
                {'text': text, 'is_correct': (col_idx + 1) in correct_indexes}
                for col_idx, col in enumerate(OPTION_COLUMNS)
                if (text := (row.get(col) or '').strip())
            ],
        })

    if not rows:
        raise CsvImportError('No valid question rows found in CSV.')
    return rows


def _insert_questions(bank, rows, sanitize=True):
    for idx, row in enumerate(rows):
        question = Question.objects.create(
            bank=bank,
            category=row.get('category', ''),
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
def import_csv(csv_text, bank_name, source_filename=None, owner=None):
    rows = parse_rows(csv_text)
    bank = QuestionBank.objects.create(name=bank_name, source_filename=source_filename, owner=owner)
    _insert_questions(bank, rows)
    return bank.id, len(rows)


@transaction.atomic
def replace_bank_questions(bank, csv_text):
    """Wholesale-replace a bank's questions. Clears in-progress instances for all exams
    sourced from this bank since their saved question IDs go stale."""
    rows = parse_rows(csv_text)
    bank.questions.all().delete()
    _insert_questions(bank, rows)
    InProgressInstance.objects.filter(exam__question_bank=bank).delete()
    return len(rows)


def export_bank_to_csv(bank):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(HEADER)
    for question in bank.questions.order_by('sort_order').prefetch_related('options'):
        options = list(question.options.order_by('sort_order'))
        correct_indexes = ','.join(str(i + 1) for i, o in enumerate(options) if o.is_correct)
        option_cells = [options[i].option_text if i < len(options) else '' for i in range(len(OPTION_COLUMNS))]
        writer.writerow([
            question.question_text,
            'Checkbox' if question.question_type == Question.MULTI else 'Multiple Choice',
            question.category,
            *option_cells,
            correct_indexes,
            question.points,
            question.image_link or '',
            question.explanation or '',
        ])
    return buf.getvalue()
