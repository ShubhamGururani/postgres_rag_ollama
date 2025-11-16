def heuristic_sql(question: str) -> str | None:
    q = question.lower()

    if "how many loans" in q:
        return "SELECT COUNT(*) AS total_loans FROM loans;"

    if "how many borrowers" in q and "india" in q:
        # <-- Fix for your failing example
        return "SELECT COUNT(*) AS total FROM borrowers WHERE country = 'India';"

    if "average disbursement" in q and "per loan" not in q:
        return "SELECT AVG(amount) AS avg_disbursement FROM disbursements;"

    if "average disbursement" in q and "per loan" in q:
        return """
        SELECT AVG(total_disbursed) AS avg_disbursed_per_loan
        FROM (
            SELECT loan_id, SUM(amount) AS total_disbursed
            FROM disbursements
            GROUP BY loan_id
        ) sub;
        """

    return None
