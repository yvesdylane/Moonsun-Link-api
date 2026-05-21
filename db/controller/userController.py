from db.connect import conn

def get_user_by_phone(phone):
    cur = conn.cursor()
    query = """select * from users where phone = %s or telegram_number = %s or whatsapp_number = %s"""
    cur.execute(query, (phone, phone, phone))
    user = cur.fetchone()
    cur.close()
    return user

def check_if_user_exist(phone):
    user = get_user_by_phone(phone)
    if user:
        return True, user[0]
    return False, None

def create_user_from_whatsapp(phone: str, name: str) -> str:
    cur = conn.cursor()
    query = """
        INSERT INTO users (name, phone, whatsapp_number, role, region, lang)
        VALUES (%s, %s, %s, 'farmer', 'General', 'en')
        RETURNING id
    """
    cur.execute(query, (name, phone, phone))
    user_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    return user_id

def get_user_role(user_id: str) -> str | None:
    cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE id = %s", (user_id,))
    result = cur.fetchone()
    cur.close()
    return result[0] if result else None