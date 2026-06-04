from db.connect import conn
from psycopg.rows import dict_row
import json

def log_message(input_text: str, intent: dict, entities: dict):
    cur = conn.cursor()
    query = """
        INSERT INTO assistant_logs (input_text, intent, confidence, method, entities)
        VALUES (%s, %s, %s, %s, %s)
    """
    cur.execute(query, (
        input_text,
        intent["intent"],
        intent["confidence"],
        intent["method"],
        json.dumps(entities)
    ))
    conn.commit()
    cur.close()


def get_assistant_logs(intent: str = None, method: str = None,
                       page: int = 1, limit: int = 20) -> dict:
    cur = conn.cursor(row_factory=dict_row)
    try:
        conditions = []
        values = []
        if intent:
            conditions.append("intent = %s")
            values.append(intent)
        if method:
            conditions.append("method = %s")
            values.append(method)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        cur.execute(f"SELECT COUNT(*) AS cnt FROM assistant_logs {where}", values)
        total = cur.fetchone()["cnt"]

        offset = (page - 1) * limit
        total_pages = max(1, -(-total // limit)) if total else 1

        cur.execute(f"""
            SELECT * FROM assistant_logs {where}
            ORDER BY timestamp DESC
            LIMIT %s OFFSET %s
        """, values + [limit, offset])
        logs = cur.fetchall()

        return {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "logs": logs,
        }
    finally:
        cur.close()


def get_assistant_log(log_id: int) -> dict | None:
    cur = conn.cursor(row_factory=dict_row)
    try:
        cur.execute("SELECT * FROM assistant_logs WHERE id = %s", (log_id,))
        return cur.fetchone()
    finally:
        cur.close()