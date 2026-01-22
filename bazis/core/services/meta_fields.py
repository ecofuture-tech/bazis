def meta_to_list(meta: str = None) -> list:
    """
    Converts a comma-separated string into a list of trimmed strings. If the input
    is None or an empty string, returns an empty list.

    Tags: RAG, EXPORT
    """
    if not meta:
        return []
    return [it.strip() for it in meta.split(',') if it.strip()]
