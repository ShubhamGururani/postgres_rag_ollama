# llm/prompts.py
import textwrap

# ============================================================
# Column Definitions (Exact Truth)
# ============================================================

COLUMN_MEANINGS = """
COLUMN DEFINITIONS (FULL TRUTH):

TABLE borrowers:
  id            → integer, primary key of borrowers
  name          → text, borrower name
  email         → text, unique borrower email
  country       → text, borrower country
  credit_score  → integer, borrower credit score

TABLE loans:
  id            → integer, primary key of loans
  borrower_id   → integer, FK → borrowers.id
  principal     → numeric, loan amount borrowed ,loan amount.
  interest_rate → numeric, interest rate
  status        → text, loan status (e.g., active / repaid / default / defaulted)
  created_at    → date, when the loan was created

TABLE disbursements:
  id            → integer, primary key
  loan_id       → integer, FK → loans.id
  amount        → numeric, amount disbursed (disbursement amount)
  disbursed_at  → date, disbursement date

TABLE payments:
  id            → integer, primary key
  loan_id       → integer, FK → loans.id
  amount        → numeric, payment amount
  paid_at       → date, payment date
  status        → text, payment status (success / failed / etc)
"""

# ============================================================
# Semantic Rules (Meaning of Each Question Type)
# ============================================================

SQL_SEMANTIC_RULES = """
SEMANTIC RULES (INTERPRETATION RULES):

1. "loan amount" ALWAYS means: loans.principal
2. "principal"  ALWAYS means: loans.principal
3. "disbursement amount" ALWAYS means: disbursements.amount
4. "payment amount" ALWAYS means: payments.amount

5. "number of loans"          → SELECT COUNT(*) FROM loans;
6. "number of borrowers"      → SELECT COUNT(*) FROM borrowers;
7. "number of payments"       → SELECT COUNT(*) FROM payments;
8. "number of disbursements"  → SELECT COUNT(*) FROM disbursements;

9. "average loan amount"            → SELECT AVG(principal) FROM loans;
10. "average payment amount"        → SELECT AVG(amount) FROM payments;
11. "average disbursement amount"   → SELECT AVG(amount) FROM disbursements;

12. "average X per loan" MUST be:
      SELECT AVG(total_x)
      FROM (
          SELECT loan_id, SUM(amount) AS total_x
          FROM <table>
          GROUP BY loan_id
      ) sub;

    Examples:
      • average disbursement per loan:
          SELECT AVG(total_disbursed)
          FROM (
              SELECT loan_id, SUM(amount) AS total_disbursed
              FROM disbursements
              GROUP BY loan_id
          ) sub;

      • average payment per loan:
          SELECT AVG(total_payment)
          FROM (
              SELECT loan_id, SUM(amount) AS total_payment
              FROM payments
              GROUP BY loan_id
          ) sub;

13. NEVER invent formulas (e.g., principal * interest_rate).
14. loans.status is the ONLY loan status column.
15. payments.status is ONLY payment status, never loan status.
16. If a question can be answered from ONE table, DO NOT use joins.
"""

# ============================================================
# SQL Structural Rules (Allowed Joins, Allowed Patterns)
# ============================================================

SQL_STRUCTURE_RULES = """
SQL CONSTRUCTION RULES:

GENERAL:
  - If question asks for an AVERAGE → use AVG(...) and return ONE numeric row.
  - If question asks for a COUNT   → use COUNT(...) and return ONE numeric row.
  - If question asks for a SUM     → use SUM(...) and return ONE numeric row.
  - If question asks to "list"     → use SELECT ... FROM ... [JOIN ...] LIMIT 50.

VALID JOINS ONLY:
  borrowers.id = loans.borrower_id
  loans.id     = payments.loan_id
  loans.id     = disbursements.loan_id

NEVER ALLOWED (INVALID JOINS):
  - loans self-join
  - borrowers self-join
  - payments self-join
  - disbursements self-join
  - loans.id = loans.borrower_id
  - ANY invented join keys

JOIN USAGE:
  - Only add JOINs when the question needs columns from multiple tables.
  - If one-table solution is enough (e.g., "average loan amount") → NO JOIN.

LIMIT RULES:
  - Aggregations (COUNT / AVG / SUM / MIN / MAX) → NO LIMIT.
  - Listing rows → add LIMIT 50.
"""

# ============================================================
# Few-shot examples (to bias the model toward correct patterns)
# ============================================================

SQL_FEWSHOTS = """
EXAMPLES (FOLLOW THESE PATTERNS):

Q: "what is the average loan amount?"
A: SELECT AVG(principal) FROM loans;

Q: "how many borrowers are there?"
A: SELECT COUNT(*) FROM borrowers;

Q: "what is the average disbursement amount?"
A: SELECT AVG(amount) FROM disbursements;

Q: "what is the average disbursement amount per loan?"
A:
SELECT AVG(total_disbursed)
FROM (
    SELECT loan_id, SUM(amount) AS total_disbursed
    FROM disbursements
    GROUP BY loan_id
) sub;

Q: "what are the different loan statuses?"
A: SELECT DISTINCT status FROM loans;
"""

PER_ENTITY_RULES = """
PER-ENTITY SQL RULES (MUST FOLLOW EXACT PATTERN):

1. "average X per loan" MUST use this pattern:
   SELECT AVG(total_x)
   FROM (
       SELECT loan_id, SUM(amount) AS total_x
       FROM <table>
       GROUP BY loan_id
   ) sub;

2. "average X per borrower" MUST use:
   SELECT AVG(total_x)
   FROM (
       SELECT borrower_id, SUM(amount) AS total_x
       FROM <table> t
       JOIN loans l ON t.loan_id = l.id
       GROUP BY borrower_id
   ) sub;

3. "number of X per loan" MUST use:
   SELECT AVG(cnt)
   FROM (
       SELECT loan_id, COUNT(*) AS cnt
       FROM <table>
       GROUP BY loan_id
   ) sub;

4. NEVER flatten the per-loan logic into a single-level SUM() or AVG().
5. NEVER join unnecessary tables — only join when borrower_id is needed.
6. NEVER join payments to disbursements.
7. NEVER join tables that are irrelevant to the question.
8. NEVER attempt formulas like principal * interest_rate.
"""


# ============================================================
# SQL GENERATION PROMPT
# ============================================================
def build_sql_generation_prompt(question, schema_summary, table_columns):
    col_dict = "\n".join(
        f"{tbl}: {', '.join(cols)}"
        for tbl, cols in table_columns.items()
    )

    return f"""
You generate ONE PostgreSQL SELECT query (or NO_SQL). 
Never output explanations or comments.

========================================
ABSOLUTE COLUMN MEANINGS (CANNOT VIOLATE)
========================================

LOAN AMOUNT:
- The ONLY column representing loan amount is: loans.principal
- “loan amount”, “amount of loan”, “borrowed amount”, “principal amount”
  ALWAYS map to loans.principal
- NEVER use disbursements.amount or payments.amount for loan amount

DISBURSEMENTS:
- disbursements.amount = disbursed amount ONLY
- NEVER treat disbursed amount as loan amount

PAYMENTS:
- payments.amount = payment amount ONLY
- NEVER treat payment amount as loan amount

========================================
VALID JOINS (ONLY these)
========================================
borrowers.id       = loans.borrower_id
loans.id           = disbursements.loan_id
loans.id           = payments.loan_id

INVALID forever:
- loans self join
- ANY self-join
- ANY invented keys
- loans.id = loans.borrower_id
- joining disbursements ↔ payments directly
HARD SQL RULE:
- Every SELECT must include a FROM clause.
If selecting columns from table X → the FROM clause must include ONLY table X unless question requires joins.
If SQL contains loans.<column>, the FROM clause MUST be: FROM loans
(and never borrowers/disbursements/payments unless required).



========================================
SEMANTIC RULES
========================================
• “average loan amount” → AVG(loans.principal)
• “loan amount” ALWAYS → loans.principal
• “average disbursement amount” → AVG(disbursements.amount)
• “average payment amount” → AVG(payments.amount)

• If question can be answered by ONE table → DO NOT JOIN. Always prefer simpler queries and never forget from clause.

========================================
SCHEMA:
{schema_summary}

COLUMNS:
{col_dict}

QUESTION:
{question}

Output only SQL or NO_SQL.
SQL:
"""


# ============================================================
# SQL VALIDATION PROMPT
# ============================================================
SINGLE_TABLE_RULE = """
SINGLE TABLE RULE (MANDATORY):
- If the question can be answered using ONE table, the SQL MUST use ONLY that table.
- Extra JOINs MUST be removed.
- Examples:
    “average loan amount” → USE ONLY loans
    “count borrowers”     → USE ONLY borrowers
    “sum of disbursements”→ USE ONLY disbursements
"""

def build_sql_validation_prompt(question, schema, sql):
    return f"""
You are a SQL validator.

Allowed outputs:
  SQL_OK
  NO_SQL
  <corrected SELECT query>

RULES:
- If SQL correctly answers the question → SQL_OK.
- If SQL is missing FROM → add correct FROM with only required table.
- If SQL references only one table → you MUST remove all JOINs.
- NEVER add JOINs unless question explicitly needs data from multiple tables.
- Correct SQL MUST use ONLY real tables/columns.
{SINGLE_TABLE_RULE}

SCHEMA:
{schema}

QUESTION:
{question}

SQL TO VALIDATE:
{sql}

Output only: SQL_OK, NO_SQL, or corrected SQL.
"""



# ============================================================
# SQL FIX PROMPT (execution failure auto-fix)
# ============================================================

def build_sql_fix_prompt(question: str, bad_sql: str, error: str, schema_summary: str) -> str:
    return f"""
The following SQL query FAILED at execution.

QUESTION:
{question}

SCHEMA:
{schema_summary}

BAD SQL:
{bad_sql}

ERROR:
{error}

You MUST return ONE corrected PostgreSQL SELECT query that:
  - Uses only real tables/columns.
  - Uses only valid joins:
        borrowers.id = loans.borrower_id
        loans.id     = disbursements.loan_id
        loans.id     = payments.loan_id
  - Is as SIMPLE as possible.
  - Answers the question according to the semantic rules:

{SQL_SEMANTIC_RULES}
{PER_ENTITY_RULES}
NO explanations. NO markdown. NO comments.
Output ONLY the corrected SELECT query.
Corrected SQL:
"""

# ============================================================
# ANSWER PROMPT
# ============================================================

def build_answer_prompt(question, sql, sql_result):
    return f"""
You are a STRICT data analyst.

RULES:
- Use ONLY SQL_RESULT
- NO hallucinations
- If SQL_RESULT starts with "SQL ERROR" → explain the error simply
- If "No results." → say exactly that
- If single aggregate (count/avg/sum) → restate value in one short sentence
- If multiple rows → summarize pattern only

QUESTION: {question}

SQL_RESULT:
{sql_result}

Answer:
"""


# ============================================================
# ANSWER FIX PROMPT
# ============================================================

def build_answer_fix_prompt(question: str, sql: str, sql_result: str, bad_answer: str) -> str:
    return f"""
Your previous answer was incorrect or contradicted SQL_RESULT.

You MUST fix it using ONLY SQL_RESULT.

QUESTION:
{question}

SQL:
{sql}

SQL_RESULT:
{sql_result}

BAD_ANSWER:
{bad_answer}

RULES:
  - No hallucinations.
  - No contradictions.
  - If SQL_RESULT is a single aggregate (e.g. "avg: 10503.8975"):
        Explain exactly that number.
  - If SQL_RESULT is "No results.", say so.
  - Keep answer short (1–3 sentences).

Corrected answer:
"""
