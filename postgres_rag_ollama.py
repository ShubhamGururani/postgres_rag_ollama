import os
import psycopg2
import textwrap
import requests


# ============================================================
# CONFIGURATION
# ============================================================

PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = int(os.environ.get("PG_PORT", "5432"))
PG_DB   = os.environ.get("PG_DB",   "ragtest")
PG_USER = os.environ.get("PG_USER", "rag_reader")
PG_PASS = os.environ.get("PG_PASS", "password")

OLLAMA_HOST  = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:1b")


# ============================================================
# OLLAMA CALLER
# ============================================================

def call_ollama(prompt: str, model: str = OLLAMA_MODEL) -> str:
    """Call Ollama /api/generate and return the text response."""
    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return (data.get("response") or "").strip()
    except Exception as e:
        return f"[OLLAMA_ERROR] {e}"


# ============================================================
# POSTGRES HELPERS
# ============================================================

def get_pg_connection():
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASS,
    )


def get_table_column_map() -> dict:
    """
    Returns:
    {
        "borrowers": ["id", "name", ...],
        "loans": [...],
        ...
    }
    """
    conn = get_pg_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position;
        """
    )
    mapping = {}
    for table, column in cur.fetchall():
        mapping.setdefault(table, []).append(column)

    conn.close()
    return mapping


def build_schema_text(table_columns: dict) -> str:
    """Render schema as readable text for the LLM."""
    parts = []
    for table, cols in table_columns.items():
        col_list = ", ".join(cols)
        parts.append(f"Table {table}: {col_list}")
    return "\n".join(parts)


def run_sql_query(sql: str) -> str:
    """
    Execute SELECT-only SQL and return a human-readable string.
    Format:
      col1: value1
      col2: value2

      col1: value1
      col2: value2
    """
    sql_clean = sql.strip().rstrip(";")

    # Hard safety: SELECT only
    if not sql_clean.lower().startswith("select"):
        return "SQL ERROR: Only SELECT statements allowed."

    try:
        conn = get_pg_connection()
        cur = conn.cursor()
        cur.execute(sql_clean)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        conn.close()

        if not rows:
            return "No results."

        out_lines = []
        for row in rows:
            out_lines.append("\n".join(f"{cols[i]}: {row[i]}" for i in range(len(cols))))
        return "\n\n".join(out_lines)

    except Exception as e:
        return f"SQL ERROR: {e}"


# ============================================================
# SANITIZER
# ============================================================

def sanitize_sql_output(text: str) -> str:
    """Strip markdown fences/backticks and whitespace."""
    if not text:
        return ""
    for bad in ["```sql", "```", "`"]:
        text = text.replace(bad, "")
    return text.strip()


def extract_first_select(text: str) -> str:
    """
    From an LLM response, pull out the first 'select ...' statement (any case),
    discarding commentary / bullets above or below.
    """
    if not text:
        return ""
    lowered = text.lower()
    idx = lowered.find("select")
    if idx == -1:
        return text.strip()
    return text[idx:].strip()


# ============================================================
# PROMPTS
# ============================================================

def build_sql_generation_prompt(
    question: str,
    schema_summary: str,
    table_columns: dict,
) -> str:
    col_dict_text = "\n".join(
        f"{tbl}: {', '.join(cols)}"
        for tbl, cols in table_columns.items()
    )

    return textwrap.dedent(f"""
    You are an expert PostgreSQL query generator.

    DATABASE SCHEMA (tables and columns):
    {schema_summary}

    COLUMN DICTIONARY (STRICT — ONLY these columns exist):
    {col_dict_text}

    DETAILED COLUMN MEANINGS (TRUTH, DO NOT INVENT):

    borrowers:
      id            -> primary key of borrower
      name          -> full name of borrower
      email         -> unique email address
      country       -> borrower country
      credit_score  -> numeric credit rating

    loans:
      id            -> primary key of loan
      borrower_id   -> FK to borrowers.id
      principal     -> amount borrowed
      interest_rate -> interest rate
      status        -> loan status (this is the ONLY loan status column)
      created_at    -> loan origination date

    payments:
      id            -> primary key of payment
      loan_id       -> FK to loans.id
      amount        -> payment amount
      paid_at       -> payment date
      status        -> payment status (NOT loan status)

    disbursements:
      id            -> primary key of disbursement
      loan_id       -> FK to loans.id
      amount        -> disbursed amount
      disbursed_at  -> disbursement date


    JOIN RULES (NON-NEGOTIABLE):
    - VALID joins only:
        borrowers.id      = loans.borrower_id
        loans.id          = payments.loan_id
        loans.id          = disbursements.loan_id
    - NEVER self-join a table to itself (no loans JOIN loans).
    - NEVER join loans.id = loans.borrower_id.
    - If one table is enough to answer, DO NOT use joins.

    SEMANTIC RULES:
    - "loan status"      -> loans.status
    - "payment amount"   -> payments.amount
    - "disbursed amount" -> disbursements.amount
    - "per loan"         -> first aggregate by loan_id, then aggregate that result.
      Example:
        Average disbursement PER LOAN:
          SELECT AVG(total_amount)
          FROM (
              SELECT loan_id, SUM(amount) AS total_amount
              FROM disbursements
              GROUP BY loan_id
          ) sub;

        Average payment PER LOAN:
          SELECT AVG(total_payment)
          FROM (
              SELECT loan_id, SUM(amount) AS total_payment
              FROM payments
              GROUP BY loan_id
          ) sub;

    SQL RULES:
    1. Generate EXACTLY ONE PostgreSQL SELECT query that answers the question.
    2. Use ONLY columns that exist in the dictionary. DO NOT invent columns.
    3. Use ONLY valid joins listed above if needed.
    4. If the question asks for:
         - total / count / average / sum / max / min
         -> use aggregation (COUNT, AVG, SUM, etc.) WITHOUT LIMIT.
       If the question asks for listing rows
         -> add LIMIT 50.
    5. Use table aliases when joining:
         borrowers      AS b
         loans          AS l
         payments       AS p
         disbursements  AS d
    6. Do NOT invent formulas with arbitrary math unless clearly implied.
    7. Use the simplest correct query.

    If and only if the question truly CANNOT be answered from this schema, output:
      NO_SQL

    IMPORTANT OUTPUT RULES:
    - Output MUST be either:
        * a single SELECT query, or
        * exactly the token: NO_SQL
    - NO explanations
    - NO commentary
    - NO markdown
    - NO prose, only SQL or NO_SQL.

    USER QUESTION:
    "{question}"

    SQL:
    """)


def build_sql_validation_prompt(question: str, schema_summary: str, sql: str) -> str:
    return textwrap.dedent(f"""
    You are a STRICT PostgreSQL validator and fixer.

    GOAL:
    - Decide if the provided SQL correctly answers the user's question.
    - If correct, output exactly: SQL_OK
    - If incorrect but fixable, output ONLY a corrected SELECT query.
    - If impossible from the schema, output exactly: NO_SQL

    HARD RULES:
    - Your reply MUST be one of:
        SQL_OK
        NO_SQL
        <a single valid SELECT query>
    - DO NOT include any explanation, markdown, bullets, or extra text.
    - If you output SQL, it MUST start with SELECT.
    - Use only real tables/columns from the schema.

    SCHEMA:
    {schema_summary}

    USER QUESTION:
    {question}

    CANDIDATE SQL:
    {sql}

    Your output (SQL_OK, NO_SQL, or corrected SELECT):
    """)


def build_sql_fix_prompt(question: str, bad_sql: str, error: str, schema_summary: str) -> str:
    return textwrap.dedent(f"""
    The following SQL query FAILED when executed.

    USER QUESTION:
    {question}

    SCHEMA:
    {schema_summary}

    BAD SQL:
    {bad_sql}

    ERROR:
    {error}

    You MUST return a corrected PostgreSQL SELECT query that:
    - Uses only tables/columns from the schema.
    - Respects the join rules:
        borrowers.id      = loans.borrower_id
        loans.id          = payments.loan_id
        loans.id          = disbursements.loan_id
    - Does NOT use INSERT/UPDATE/DELETE, only SELECT.
    - Answers the user's question.

    OUTPUT RULE:
    - Return ONLY a single valid SELECT query.
    - NO explanation, NO markdown, NO comments, only SQL.

    Corrected SQL:
    """)


def build_answer_prompt(question: str, sql: str, sql_result: str) -> str:
    return textwrap.dedent(f"""
    You are a STRICT data analyst.

    Your job is to explain the SQL result to the user.

    RULES:
    - NEVER hallucinate values.
    - ONLY use information present in SQL_RESULT.
    - If SQL_RESULT starts with "SQL ERROR:", explain the error in plain language.
    - If SQL_RESULT is exactly "No results.", say that no rows matched.
    - If SQL_RESULT is one numeric aggregate like:
        "avg: 10503.8975"
      then:
        - Identify the metric correctly (average / count / sum etc.)
        - Explain in one sentence, rounded to 2 decimals.
    - If multiple rows/columns are returned, summarize the key insight.
    - Keep the answer short and factual (2–4 sentences max).
    - DO NOT invent counts or values that are not in SQL_RESULT.

    QUESTION:
    {question}

    SQL EXECUTED:
    {sql}

    SQL_RESULT:
    {sql_result}

    Final answer to the user:
    """)


def build_answer_fix_prompt(question: str, sql: str, sql_result: str, bad_answer: str) -> str:
    return textwrap.dedent(f"""
    Your previous answer was incorrect or contradicted the SQL result.

    You MUST correct your answer using ONLY SQL_RESULT.

    QUESTION:
    {question}

    SQL EXECUTED:
    {sql}

    SQL_RESULT:
    {sql_result}

    BAD_ANSWER:
    {bad_answer}

    RULES:
    - DO NOT hallucinate.
    - DO NOT contradict SQL_RESULT.
    - If SQL_RESULT clearly contains a single aggregate (like avg: X or count: Y),
      state that number correctly in plain English.
    - If SQL_RESULT is "No results.", say exactly that.
    - Answer in 1–3 concise sentences.

    Provide ONLY the corrected answer text, nothing else:
    """)


# ============================================================
# AGENT LOGIC
# ============================================================

def generate_sql_for_question(question: str, schema_summary: str, table_columns: dict) -> str:
    prompt = build_sql_generation_prompt(question, schema_summary, table_columns)
    raw = call_ollama(prompt)
    sql = sanitize_sql_output(raw)
    # For safety, if it contains a SELECT, extract only that
    if "select" in sql.lower():
        sql = extract_first_select(sql)
    return sql or "NO_SQL"


def validate_sql(question: str, schema_summary: str, candidate_sql: str) -> str:
    """
    Run a SQL validator/fixer:
      - If it returns SQL_OK → keep candidate_sql
      - If it returns NO_SQL → NO_SQL
      - If it returns a SELECT → use that as corrected SQL
    """
    prompt = build_sql_validation_prompt(question, schema_summary, candidate_sql)
    resp = call_ollama(prompt)
    cleaned = sanitize_sql_output(resp)

    # If the model sneaks commentary, try to salvage a SELECT
    if "select" in cleaned.lower():
        return extract_first_select(cleaned)

    up = cleaned.strip().upper()
    if up == "SQL_OK":
        return candidate_sql
    if up == "NO_SQL":
        return "NO_SQL"

    # Fallback: if the cleaned string itself looks like SQL, use it
    if cleaned.lower().startswith("select"):
        return cleaned

    return "NO_SQL"


def generate_final_answer(question: str, sql: str, sql_result: str) -> str:
    # If SQL itself failed, don't ask LLM to interpret nonsense
    if sql_result.startswith("SQL ERROR:"):
        return f"There was an error executing the SQL query:\n{sql_result}"

    prompt = build_answer_prompt(question, sql, sql_result)
    answer = call_ollama(prompt).strip()

    # Simple contradiction detector: if LLM says “No results” but DB clearly returned rows
    contradiction = (
        ("no results" in answer.lower())
        and (sql_result.strip() != "No results.")
    )

    if contradiction:
        fix_prompt = build_answer_fix_prompt(question, sql, sql_result, answer)
        answer = call_ollama(fix_prompt).strip()

    return answer


# ============================================================
# MAIN LOOP
# ============================================================

def main():
    print("\n=== Local Postgres RAG Agent (Ollama) ===\n")

    print("Loading table/column metadata...")
    table_columns = get_table_column_map()
    schema_summary = build_schema_text(table_columns)

    print("\nDetected schema:\n")
    print(schema_summary)
    print("\nAsk your questions. Type 'quit' to exit.\n")

    while True:
        question = input("Your question: ").strip()
        if question.lower() in ("quit", "exit"):
            print("Goodbye!")
            break

        # 1) Generate SQL
        sql = generate_sql_for_question(question, schema_summary, table_columns)
        print("\n[DEBUG] SQL Generated:\n", sql, "\n")

        # 2) Validate / possibly correct SQL
        corrected_sql = validate_sql(question, schema_summary, sql)
        print("[DEBUG] Validated SQL:\n", corrected_sql, "\n")

        if corrected_sql == "NO_SQL":
            print("Agent: This question cannot be answered from this database.\n")
            print("=" * 60 + "\n")
            continue

        if corrected_sql.startswith("[OLLAMA_ERROR]"):
            print("Agent: LLM error while validating SQL:")
            print(corrected_sql)
            print("=" * 60 + "\n")
            continue

        # 3) Execute SQL (first attempt)
        sql_result = run_sql_query(corrected_sql)
        print("[DEBUG] SQL Result:\n", sql_result, "\n")

        # 4) If SQL failed, try one auto-fix pass
        if sql_result.startswith("SQL ERROR:"):
            print("[DEBUG] SQL ERROR detected, attempting auto-fix...\n")
            fix_prompt = build_sql_fix_prompt(
                question, corrected_sql, sql_result, schema_summary
            )
            fixed_sql_raw = call_ollama(fix_prompt)
            fixed_sql = sanitize_sql_output(fixed_sql_raw)
            if "select" in fixed_sql.lower():
                fixed_sql = extract_first_select(fixed_sql)

            print("[DEBUG] Auto-fix SQL:\n", fixed_sql, "\n")

            if fixed_sql.lower().startswith("select"):
                corrected_sql = fixed_sql
                sql_result = run_sql_query(corrected_sql)
                print("[DEBUG] SQL Result After Auto-fix:\n", sql_result, "\n")

        # 5) Final answer generation
        answer = generate_final_answer(question, corrected_sql, sql_result)

        print("Agent Response:\n", answer)
        print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    main()
