from llm.ollama_client import call_ollama
from utils.sql_utils import sanitize_sql_output, extract_first_select
from llm.prompts import build_sql_validation_prompt, build_sql_fix_prompt


def validate_sql(question, schema, sql):
    prompt = build_sql_validation_prompt(question, schema, sql)
    resp = sanitize_sql_output(call_ollama(prompt))

    if resp.upper() == "SQL_OK":
        return sql

    if resp.upper() == "NO_SQL":
        return "NO_SQL"

    # Otherwise treat as corrected SQL
    return extract_first_select(resp)


def autofix_sql(question, bad_sql, error_text, schema):
    """
    Requests a corrected SQL from LLM.
    """
    prompt = build_sql_fix_prompt(question, bad_sql, error_text, schema)
    resp = sanitize_sql_output(call_ollama(prompt))
    return extract_first_select(resp)
