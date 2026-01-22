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
