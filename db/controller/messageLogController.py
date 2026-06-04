from db.connect import conn
from psycopg.rows import dict_row

def log_message_exchange(user_id: str, incoming: str, outgoing: str, intent: str, platform: str = "whatsapp"):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO message_logs (user_id, platform, incoming_message, outgoing_reply, intent)
        VALUES (%s, %s, %s, %s, %s)
    """, (user_id, platform, incoming, outgoing, intent))
    conn.commit()
    cur.close()


def get_message_logs(platform: str = None, intent: str = None,
                     user_id: str = None,
                     page: int = 1, limit: int = 20) -> dict:
    cur = conn.cursor(row_factory=dict_row)
    try:
        conditions = []
        values = []
        if platform:
            conditions.append("platform = %s")
            values.append(platform)
        if intent:
            conditions.append("intent = %s")
            values.append(intent)
        if user_id:
            conditions.append("user_id = %s")
            values.append(user_id)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        cur.execute(f"""
            SELECT COUNT(*) AS cnt FROM message_logs ml
            LEFT JOIN users u ON ml.user_id = u.id
            {where}
        """, values)
        total = cur.fetchone()["cnt"]

        offset = (page - 1) * limit
        total_pages = max(1, -(-total // limit)) if total else 1

        cur.execute(f"""
            SELECT ml.*, u.name AS user_name, u.phone AS user_phone
            FROM message_logs ml
            LEFT JOIN users u ON ml.user_id = u.id
            {where}
            ORDER BY ml.created_at DESC
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


def get_message_log(log_id: int) -> dict | None:
    cur = conn.cursor(row_factory=dict_row)
    try:
        cur.execute("""
            SELECT ml.*, u.name AS user_name, u.phone AS user_phone
            FROM message_logs ml
            LEFT JOIN users u ON ml.user_id = u.id
            WHERE ml.id = %s
        """, (log_id,))
        return cur.fetchone()
    finally:
        cur.close()