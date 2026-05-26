from db.connect import conn
from db.models.user import User
from typing import Optional

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
        VALUES (%s, %s, %s, 'buyer', 'General', 'en')
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

def get_user_by_telegram(telegram_id: str):
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
    user = cur.fetchone()
    cur.close()
    return user

def check_if_user_exist_by_telegram(telegram_id: str):
    user = get_user_by_telegram(telegram_id)
    if user:
        return True, user[0]
    return False, None

def create_user_from_telegram(telegram_id: str, name: str, phone: str = None, region: str = "General") -> str:
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (name, telegram_id, phone, role, region, lang)
        VALUES (%s, %s, %s, 'buyer', %s, 'en')
        RETURNING id
    """, (name, telegram_id, phone, region))
    user_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    return user_id

def link_telegram_to_account(phone: str, telegram_id: str) -> dict:
    user = get_user_by_phone(phone)
    if not user:
        return {"status": "error", "message": "No account found"}
    cur = conn.cursor()
    cur.execute("UPDATE users SET telegram_id = %s WHERE id = %s", (telegram_id, user[0]))
    conn.commit()
    cur.close()
    return {"status": "ok", "name": user[2]}

def get_user_info(user_id: str) -> Optional[User]:
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    row = cur.fetchone()
    cur.close()
    return User.from_db_row(row) if row else None

def update_user_info(user_id: str, updates: dict) -> dict:
    if not updates:
        return {"status": "error", "message": "Nothing to update"}

    fields = [f"{key} = %s" for key in updates.keys()]
    values = list(updates.values())
    values.append(user_id)

    query = f"UPDATE users SET {', '.join(fields)}, updated_at = NOW() WHERE id = %s RETURNING *"

    cur = conn.cursor()
    cur.execute(query, values)
    updated = cur.fetchone()
    conn.commit()
    cur.close()

    if not updated:
        return {"status": "error", "message": "User not found"}
    return {"status": "ok", "message": "Profile updated successfully", "user": updated}

def change_role_to_farmer(user_id: str, region: str) -> dict:
    if region.lower() == "general":
        return {"status": "error", "message": "Please specify your primary region of activity (e.g., Littoral, Center, West, etc.). 'General' is not accepted for farmers."}

    cur = conn.cursor()
    cur.execute("""
        UPDATE users
        SET role = 'farmer', region = %s, updated_at = NOW()
        WHERE id = %s
        RETURNING verified
    """, (region, user_id))
    result = cur.fetchone()
    conn.commit()
    cur.close()

    if not result:
        return {"status": "error", "message": "User not found"}

    verified = result[0]
    if verified != 'true':
        return {
            "status": "ok",
            "message": "✅ Your account has been upgraded to Farmer!\n\n⚠️ Note: Your listings will NOT be visible to buyers until you verify your account. Send 'verify my account' to start the verification process.",
            "needs_verification": True
        }

    return {"status": "ok", "message": "✅ Your account has been upgraded to Farmer! You can now create listings."}

def submit_verification_files(user_id: str, selfie_url: str, id_url: str) -> dict:
    """
    Submit verification files and set user status to 'pending'.
    The files should already be uploaded to Cloudinary at moonso/users/{user_id}/.
    """
    cur = conn.cursor()
    cur.execute("""
        UPDATE users
        SET pic_folder = %s, verified = 'pending', updated_at = NOW()
        WHERE id = %s
        RETURNING id
    """, (f"moonso/users/{user_id}", user_id))
    result = cur.fetchone()
    conn.commit()
    cur.close()

    if not result:
        return {"status": "error", "message": "User not found"}

    return {
        "status": "ok",
        "message": "✅ Verification files submitted successfully!\n\nYour account status is now: ⏳ Pending Review\n\nOur team will review your documents. You'll be notified once verified. After verification, buyers will be able to see your listings."
    }

def check_verification_status(user_id: str) -> dict:
    cur = conn.cursor()
    cur.execute("SELECT verified, role, pic_folder FROM users WHERE id = %s", (user_id,))
    result = cur.fetchone()
    cur.close()

    if not result:
        return {"status": "error", "message": "User not found"}

    verified, role, pic_folder = result

    if role != "farmer":
        return {"status": "ok", "message": "Verification is only required for farmers. Switch to farmer role to create listings."}

    if verified == 'true':
        return {"status": "ok", "message": "✅ Your account is verified! You can create listings that are visible to all buyers."}

    if verified == 'pending':
        return {"status": "ok", "message": "⏳ Your verification is pending review. We'll notify you once approved."}

    return {
        "status": "ok",
        "message": "❌ Your account is not verified yet.\n\nTo verify, send: 'verify my account'\n\nYou'll need to provide:\n1. A clear selfie photo\n2. A photo of your ID card\n\nAccepted formats: JPEG, PNG, PDF (max 2MB each)\n\nWithout verification, buyers cannot see your listings."
    }