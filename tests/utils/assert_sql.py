# Copyright 2026 EcoFuture Technology Services LLC and contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re

from django.db.backends import utils
from django.db.backends.base.base import BaseDatabaseWrapper

import sqlparse


def force_debug_cursor(self, cursor):
    return utils.CursorDebugWrapper(cursor, self)


BaseDatabaseWrapper.make_debug_cursor = force_debug_cursor
BaseDatabaseWrapper.make_cursor = force_debug_cursor


def get_sql_query(query_numbers: list[int] | None = None) -> list[str] | str:
    """Returns SQL query from sql.log."""
    if query_numbers is None:
        query_numbers = [-1]
    with open('sql.log') as f:
        sql_queries = f.readlines()

    print('\n'.join(sql_queries))

    if not sql_queries:
        return ''
    prepared_queries = []
    for query_number in query_numbers:
        sql_query = sql_queries[query_number].strip()
        formatted_query = sqlparse.format(sql_query, reindent=True, keyword_case='upper')

        sql_pattern = re.compile(r'SELECT\s.*?\sLIMIT\s\d+;', re.DOTALL | re.IGNORECASE)
        sql_match = sql_pattern.search(formatted_query)
        if sql_match is None:
            # Remove the first line with the timestamp (in parentheses)
            if formatted_query.startswith('('):
                lines = formatted_query.split('\n', 1)
                formatted_query = lines[1] if len(lines) > 1 else ''
                lines = formatted_query.split(';', 1)
                formatted_query = lines[0] if len(lines) > 1 else ''
        else:
            formatted_query = sql_match.group(0)
        prepared_queries.append(formatted_query)

    return prepared_queries if len(prepared_queries) > 1 else prepared_queries[0]


_QUOTED_ALIAS_RE = re.compile(r'"([a-z]\d+)"')


def _split_top_level(expr: str) -> list[str]:
    """Splits an expression by commas that are not nested in parentheses or quotes."""
    parts, depth, quote, start = [], 0, None, 0
    for i, ch in enumerate(expr):
        if quote:
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
        elif ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif ch == ',' and depth == 0:
            parts.append(expr[start:i].strip())
            start = i + 1
    parts.append(expr[start:].strip())
    return parts


def _find_closing_paren(sql: str, open_idx: int) -> int:
    depth, quote = 0, None
    for i in range(open_idx, len(sql)):
        ch = sql[i]
        if quote:
            if ch == quote:
                quote = None
        elif ch in ('"', "'"):
            quote = ch
        elif ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                return i
    raise ValueError(f'Unbalanced parentheses in SQL: {sql}')


def _json_object_to_jsonb_build_object(sql: str) -> str:
    """
    Converts the native ``JSON_OBJECT((key) VALUE value, ... RETURNING JSONB)`` syntax,
    which Django emits on PostgreSQL 16+, into the equivalent ``JSONB_BUILD_OBJECT(key, value)``
    form emitted for older PostgreSQL servers.
    """
    marker = 'json_object('
    while (idx := sql.find(marker)) != -1:
        open_idx = idx + len(marker) - 1
        close_idx = _find_closing_paren(sql, open_idx)
        inner = _json_object_to_jsonb_build_object(sql[open_idx + 1 : close_idx])
        inner = re.sub(r'\s+returning\s+jsonb\s*$', '', inner)
        args = []
        for pair in _split_top_level(inner):
            key, value = pair.split(' value ', 1)
            key = key.strip()
            if key.startswith('(') and _find_closing_paren(key, 0) == len(key) - 1:
                key = key[1:-1]
            args.extend((key, value.strip()))
        sql = f'{sql[:idx]}jsonb_build_object({", ".join(args)}){sql[close_idx + 1 :]}'
    return sql


def normalize_sql(sql: str) -> str:
    """
    Normalizes SQL so that the comparison does not depend on the Django and PostgreSQL versions:
    whitespace and case are unified, subquery aliases are unquoted (Django 6.1 quotes them)
    and JSON_OBJECT is rewritten to JSONB_BUILD_OBJECT (Django uses it on PostgreSQL 16+).
    """
    sql = re.sub(r'\s+', ' ', sql.strip()).lower()
    sql = _QUOTED_ALIAS_RE.sub(r'\1', sql)
    return _json_object_to_jsonb_build_object(sql)


def assert_sql_query(expected_sql, actual_query, id_hex=None):
    if not expected_sql or not actual_query:
        return
    """Compares actual SQL query with expected template."""
    if id_hex is not None:
        expected_sql = expected_sql.replace('id_hex', id_hex)
    assert normalize_sql(actual_query) == normalize_sql(expected_sql)
