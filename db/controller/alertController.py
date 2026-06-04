from db.connect import conn
from datetime import datetime


def create_alert(
    title: str,
    alert_type: str,
    created_by: str,
    description: str = None,
    region: str = None,
    product_name: str = None,
    source_report_id: int = None,
    expires_at: str = None,
) -> dict:
    cur = conn.cursor()
    try:
        expires = datetime.fromisoformat(expires_at) if expires_at else None
        cur.execute("""
            INSERT INTO alerts (title, description, alert_type, region, product_name,
                                source_report_id, created_by, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """, (title, description, alert_type, region, product_name,
              source_report_id, created_by, expires))
        alert = cur.fetchone()
        conn.commit()
        if not alert:
            return {"status": "error", "message": "Failed to create alert"}
        return {"status": "ok", "alert": alert}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        cur.close()


def get_all_user_contacts(region: str = None) -> list[dict]:
    cur = conn.cursor()
    try:
        if region:
            cur.execute("""
                SELECT id, name, whatsapp_chat_id, telegram_id
                FROM users
                WHERE region = %s
            """, (region,))
        else:
            cur.execute("""
                SELECT id, name, whatsapp_chat_id, telegram_id
                FROM users
            """)
        return cur.fetchall()
    finally:
        cur.close()
