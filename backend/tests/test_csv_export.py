import csv
from io import StringIO

import pytest

from app.services.csv_export import spreadsheet_csv_value


@pytest.mark.parametrize('text', ['=1+1', '+SUM(1,2)', '-1+2', '@SUM(1,2)', '  =1+1', '\ufeff =1+1', '＝1+1', '＋1', '－1', '＠SUM(1,2)', '\tvalue', '\rvalue', '\nvalue', '\0value'])
def test_untrusted_formula_prefixes_receive_a_csv_only_text_marker(text):
    assert spreadsheet_csv_value(text) == '\t' + text


@pytest.mark.parametrize('value', [-75, -0.5, 0, 100, None, True, 'Recorded fact', 'Béthune', 'The result is =1+1'])
def test_ordinary_text_and_typed_numbers_remain_unchanged(value):
    assert spreadsheet_csv_value(value) == value


def test_quotes_separators_and_line_breaks_cannot_create_extra_cells():
    values = ['normal",=1+1', '=1+1";,=2+2', 'line one\n=1+1']
    output = StringIO()
    csv.writer(output, quoting=csv.QUOTE_ALL).writerow([spreadsheet_csv_value(value) for value in values])
    assert list(csv.reader(StringIO(output.getvalue()))) == [[values[0], '\t' + values[1], values[2]]]
