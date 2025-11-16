from llm.ollama_client import call_ollama
from utils.sql_utils import sanitize_sql_output, extract_first_select
from llm.heuristics import heuristic_sql
from llm.prompts import build_sql_generation_prompt


def generate_sql(question, schema_summary, table_columns):
    # 1) heuristic override first
    h = heuristic_sql(question)
    if h:
        return h

    # 2) LLM generation
    prompt = build_sql_generation_prompt(question, schema_summary, table_columns)
    raw = call_ollama(prompt)
    cleaned = sanitize_sql_output(raw)

    if cleaned.upper() == "NO_SQL":
        return "NO_SQL"

    # Extract first SELECT
    return extract_first_select(cleaned)
