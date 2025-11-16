from db.connection import get_pg_connection

def run_sql_query(sql: str) -> str:
    sql_clean = sql.strip().rstrip(";")

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

        formatted = []
        for r in rows:
            formatted.append(
                "\n".join(f"{cols[i]}: {r[i]}" for i in range(len(cols)))
            )
        return "\n\n".join(formatted)

    except Exception as e:
        return f"SQL ERROR: {e}"
