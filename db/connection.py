import psycopg2
from config import PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASS

def get_pg_connection():
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASS,
    )
