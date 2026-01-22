def include_to_list(include: str = None) -> list:
    """
    Converts a comma-separated string into a list of stripped, non-empty items. If
    the input string is None or empty, returns an empty list.

    Tags: RAG, EXPORT
    """
    if not include:
        return []
    return [it.strip() for it in include.split(',') if it.strip()]
