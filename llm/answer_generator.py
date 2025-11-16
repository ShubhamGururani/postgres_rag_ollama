from llm.ollama_client import call_ollama
from llm.prompts import build_answer_prompt, build_answer_fix_prompt


def generate_answer(question, sql, sql_result):
    if sql_result.startswith("SQL ERROR:"):
        return f"There was an error executing the SQL query:\n{sql_result}"

    answer1 = call_ollama(build_answer_prompt(question, sql, sql_result)).strip()

    # Detect contradiction
    contradiction = (
        "no results" in answer1.lower()
        and sql_result.strip() != "No results."
    )

    if contradiction:
        answer2 = call_ollama(
            build_answer_fix_prompt(question, sql, sql_result, answer1)
        ).strip()
        return answer2

    return answer1
