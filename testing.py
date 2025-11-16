import psycopg2
from psycopg2.extras import execute_values
import random
from datetime import datetime, timedelta

# ----------------------------------------------------
# CONFIG
# ----------------------------------------------------
DB_CONFIG = {
    "dbname": "ragtest",
    "user": "shubhamgururani",
    "password": "password",
    "host": "localhost",
    "port": "5432",
}

NUM_BORROWERS = 100000    # scalable
LOANS_PER_BORROWER = (1, 3)
DISBURSEMENTS_PER_LOAN = (1, 3)
PAYMENTS_PER_LOAN = (3, 20)

BATCH_SIZE = 5000   # prevents RAM blowup


# ----------------------------------------------------
# HELPERS
# ----------------------------------------------------
def random_name():
    first = random.choice([
        "Amit", "Rohan", "Priya", "Sneha", "John", "Maria",
        "Chen", "Sara", "David", "Kumar", "Raj", "Alex"
    ])
    last = random.choice([
        "Sharma", "Patel", "Singh", "Gupta", "Lee", "Brown",
        "Wilson", "Khan", "Mehta", "Joshi"
    ])
    return f"{first} {last}"


def random_date(start_year=2018):
    start = datetime(start_year, 1, 1)
    end = datetime(2025, 1, 1)
    return start + (end - start) * random.random()


# ----------------------------------------------------
# CREATE SCHEMA
# ----------------------------------------------------
def create_schema(conn):
    cur = conn.cursor()

    cur.execute("""
    DROP TABLE IF EXISTS payments;
    DROP TABLE IF EXISTS disbursements;
    DROP TABLE IF EXISTS loans;
    DROP TABLE IF EXISTS borrowers;

    CREATE TABLE borrowers (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE,
        country TEXT,
        credit_score INTEGER
    );

    CREATE TABLE loans (
        id SERIAL PRIMARY KEY,
        borrower_id INTEGER REFERENCES borrowers(id),
        principal NUMERIC(12,2),
        interest_rate NUMERIC(5,2),      -- 3.25% etc
        status TEXT,
        created_at DATE
    );

    CREATE TABLE disbursements (
        id SERIAL PRIMARY KEY,
        loan_id INTEGER REFERENCES loans(id),
        amount NUMERIC(12,2),
        disbursed_at DATE
    );

    CREATE TABLE payments (
        id SERIAL PRIMARY KEY,
        loan_id INTEGER REFERENCES loans(id),
        amount NUMERIC(12,2),
        paid_at DATE,
        status TEXT
    );
    """)

    conn.commit()
    cur.close()
    print("[OK] Schema created.")


# ----------------------------------------------------
# MAIN INSERT SCRIPT
# ----------------------------------------------------
def main():
    conn = psycopg2.connect(**DB_CONFIG)
    create_schema(conn)
    cur = conn.cursor()

    print(f"\n=== Generating dataset for {NUM_BORROWERS:,} borrowers ===")

    # ------------------------------------------------------
    # 1️⃣ INSERT BORROWERS (in batches)
    # ------------------------------------------------------
    print(f"[1/5] Inserting {NUM_BORROWERS:,} borrowers...")

    for start in range(0, NUM_BORROWERS, BATCH_SIZE):
        batch = []
        end = min(start + BATCH_SIZE, NUM_BORROWERS)

        for _ in range(start, end):
            name = random_name()
            email = name.lower().replace(" ", "_") + str(random.randint(1, 99999999999)) + "@example.com"
            country = random.choice(["India", "USA", "Mexico", "Canada", "Nigeria", "China"])
            credit_score = random.randint(550, 800)
            batch.append((name, email, country, credit_score))

        execute_values(
            cur,
            "INSERT INTO borrowers (name, email, country, credit_score) VALUES %s;",
            batch,
        )
        conn.commit()
        print(f"   Inserted {end:,}/{NUM_BORROWERS:,}")

    cur.execute("SELECT id FROM borrowers ORDER BY id;")
    borrower_ids = [row[0] for row in cur.fetchall()]
    print(f"[OK] Loaded {len(borrower_ids):,} borrower IDs.")

    # ------------------------------------------------------
    # 2️⃣ INSERT LOANS
    # ------------------------------------------------------
    print("[2/5] Generating loans…")

    loans = []
    for borrower_id in borrower_ids:
        for _ in range(random.randint(*LOANS_PER_BORROWER)):
            principal = random.randint(5000, 50000)
            interest_rate = round(random.uniform(3.0, 10.0), 2)

            loans.append((
                borrower_id,
                principal,
                interest_rate,
                random.choice(["approved", "repaid", "defaulted"]),
                random_date()
            ))

    execute_values(
        cur,
        """INSERT INTO loans (borrower_id, principal, interest_rate, status, created_at)
           VALUES %s;""",
        loans,
    )
    conn.commit()

    print(f"[OK] Inserted {len(loans):,} loans.")

    cur.execute("SELECT id FROM loans ORDER BY id;")
    loan_ids = [row[0] for row in cur.fetchall()]

    # ------------------------------------------------------
    # 3️⃣ INSERT DISBURSEMENTS
    # ------------------------------------------------------
    print("[3/5] Generating disbursements…")

    disbursements = []
    for loan_id in loan_ids:
        for _ in range(random.randint(*DISBURSEMENTS_PER_LOAN)):
            amount = random.randint(1000, 20000)
            date = random_date()
            disbursements.append((loan_id, amount, date))

    execute_values(
        cur,
        "INSERT INTO disbursements (loan_id, amount, disbursed_at) VALUES %s;",
        disbursements,
    )
    conn.commit()

    print(f"[OK] Inserted {len(disbursements):,} disbursements.")

    # ------------------------------------------------------
    # 4️⃣ INSERT PAYMENTS
    # ------------------------------------------------------
    print("[4/5] Generating payments…")

    payments = []
    for loan_id in loan_ids:
        for _ in range(random.randint(*PAYMENTS_PER_LOAN)):
            amount = random.randint(100, 2000)
            date = random_date()
            payments.append((loan_id, amount, date, random.choice(["success", "failed"])))

    execute_values(
        cur,
        "INSERT INTO payments (loan_id, amount, paid_at, status) VALUES %s;",
        payments,
    )
    conn.commit()

    print(f"[OK] Inserted {len(payments):,} payments.")

    print("\n=== DONE! DATASET GENERATED SUCCESSFULLY ===")
    print(f"Borrowers:      {len(borrower_ids):,}")
    print(f"Loans:          {len(loans):,}")
    print(f"Disbursements:  {len(disbursements):,}")
    print(f"Payments:       {len(payments):,}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
