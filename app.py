from db.schema_reader import get_table_column_map, build_schema_text
from db.executor import run_sql_query
from llm.sql_generator import generate_sql
from llm.sql_validator import validate_sql, autofix_sql
from llm.answer_generator import generate_answer


def main():
    print("\n=== Local Postgres RAG Agent (Modular Version) ===\n")

    print("Loading schema...")
    table_columns = get_table_column_map()
    schema = build_schema_text(table_columns)
    print("\nDetected schema:\n", schema, "\n")

    while True:
        question = input("Your question: ").strip()
        if question.lower() in ("quit", "exit"):
            print("Goodbye!")
            break

        # 1) Generate SQL
        sql = generate_sql(question, schema, table_columns)
        print("\n[DEBUG] SQL Generated:\n", sql)

        # 2) Validate
        validated = validate_sql(question, schema, sql)
        print("\n[DEBUG] Validated SQL:\n", validated)

        if validated == "NO_SQL":
            print("Agent: Cannot answer from this database.\n")
            continue

        # 3) Execute SQL
        result = run_sql_query(validated)
        print("\n[DEBUG] SQL Result:\n", result)

        # 4) Auto-fix if SQL failed
        if result.startswith("SQL ERROR:"):
            print("[DEBUG] SQL ERROR → auto-fixing...")
            fixed_sql = autofix_sql(question, validated, result, schema)
            print("[DEBUG] Auto-fixed SQL:\n", fixed_sql)

            if fixed_sql.lower().startswith("select"):
                validated = fixed_sql
                result = run_sql_query(validated)
                print("[DEBUG] After auto-fix result:\n", result)

        # 5) Final answer
        answer = generate_answer(question, validated, result)
        print("\nAgent:\n", answer, "\n" + "="*60 + "\n")


if __name__ == "__main__":
    main()
