"""Spreadsheet-oriented CSV encoding; original records remain unchanged.

OWASP documents a quoted leading tab as an Excel-resistant text guard:
https://community.owasp.org/attacks/CSV_Injection
The marker is part of the CSV value. JSON evidence preserves exact source text.
This is not a guarantee for every spreadsheet application's import behaviour.
"""
import re
import unicodedata

VERSION = 'spreadsheet-text-v1'


def spreadsheet_csv_value(value: object) -> object:
    if not isinstance(value, str):
        return value
    probe = re.sub(r'^[\s\ufeff]*', '', unicodedata.normalize('NFKC', value))
    if (probe and probe[0] in '=+-@') or value.startswith(('\t', '\r', '\n', '\0')):
        return '\t' + value
    return value
