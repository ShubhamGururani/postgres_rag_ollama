from db.connection import get_pg_connection

def get_table_column_map() -> dict:
    conn = get_pg_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position;
    """)

    mapping = {}
    for table, column in cur.fetchall():
        mapping.setdefault(table, []).append(column)

    conn.close()
    return mapping


def build_schema_text(table_cols: dict) -> str:
    parts = []
    for table, cols in table_cols.items():
        parts.append(f"Table {table}: {', '.join(cols)}")
    return "\n".join(parts)
