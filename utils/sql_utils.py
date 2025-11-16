def sanitize_sql_output(text: str) -> str:
    if not text:
        return ""
    for bad in ["```sql", "```", "`"]:
        text = text.replace(bad, "")
    return text.strip()


def extract_first_select(text: str) -> str:
    """
    Extract SELECT ... from any LLM output.
    """
    if not text:
        return ""
    low = text.lower()
    idx = low.find("select")
    if idx >= 0:
        return text[idx:].strip()
    return text.strip()
