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


def assert_sql_query(expected_sql, actual_query, id_hex=None):
    if not expected_sql or not actual_query:
        return
    """Compares actual SQL query with expected template."""
    if id_hex is not None:
        expected_sql = expected_sql.replace('id_hex', id_hex)
    assert (
        re.sub(r'\s+', ' ', actual_query.strip()).lower()
        == re.sub(r'\s+', ' ', expected_sql.strip()).lower()
    )
