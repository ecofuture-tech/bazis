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

import json

from pghistory import config, runtime


def _inject_history_context(execute, sql, params, many, context):
    """
    Eliminates the possibility of SQL exploit

    Tags: RAG, EXPORT
    """
    cursor = context['cursor']

    if not cursor.name and not runtime._is_concurrent_statement(sql):
        metadata_str = json.dumps(
            runtime._tracker.value.metadata, cls=config.json_encoder()
        ).replace("'", "''")

        params = (str(runtime._tracker.value.id), metadata_str) + (
            tuple(params) if params else tuple()
        )

        sql = ('SET LOCAL pghistory.context_id=%s;SET LOCAL pghistory.context_metadata=%s;') + sql

    return execute(sql, params, many, context)


runtime._inject_history_context = _inject_history_context
