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
        return True, user['id']
    return False, None


def create_user_from_whatsapp(phone: str, name: str, chat_id: str = None) -> str:
    cur = conn.cursor()
    query = """
        INSERT INTO users (name, phone, whatsapp_number, whatsapp_chat_id, role, region, lang)
        VALUES (%s, %s, %s, %s, 'buyer', 'General', 'en')
        RETURNING id
    """
    cur.execute(query, (name, phone, phone, chat_id))
    user_id = cur.fetchone()['id']
    conn.commit()
    cur.close()
    return user_id

def update_user_chat_id(user_id: str, chat_id: str):
    """Update user's WhatsApp chat_id if not already set."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE users
        SET whatsapp_chat_id = %s
        WHERE id = %s AND (whatsapp_chat_id IS NULL OR whatsapp_chat_id = '')
    """, (chat_id, user_id))
    conn.commit()
    cur.close()

def get_user_role(user_id: str) -> str | None:
    cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE id = %s", (user_id,))
    result = cur.fetchone()
    cur.close()
    return result['role'] if result else None

def get_user_by_telegram(telegram_id: str):
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
    user = cur.fetchone()
    cur.close()
    return user

def check_if_user_exist_by_telegram(telegram_id: str):
    user = get_user_by_telegram(telegram_id)
    if user:
        return True, user['id']
    return False, None

def create_user_from_telegram(telegram_id: str, name: str, telegram_number: str = None, region: str = "General") -> str:
    """
    Create user from Telegram.
    telegram_number is stored in telegram_number field, NOT phone (phone is for SMS).
    """
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (name, telegram_id, telegram_number, role, region, lang)
        VALUES (%s, %s, %s, 'buyer', %s, 'en')
        RETURNING id
    """, (name, telegram_id, telegram_number, region))
    user_id = cur.fetchone()['id']
    conn.commit()
    cur.close()
    return user_id

def check_cross_platform_account(phone_number: str) -> dict:
    """
    Check if this phone number exists on other platforms (Telegram, WhatsApp, or SMS).

    Returns:
        dict with user_id and platform if found, None otherwise
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT id, telegram_number, whatsapp_number, phone
        FROM users
        WHERE telegram_number = %s OR whatsapp_number = %s OR phone = %s
    """, (phone_number, phone_number, phone_number))
    result = cur.fetchone()
    cur.close()

    if not result:
        return None

    user_id = result['id']
    telegram_num = result['telegram_number']
    whatsapp_num = result['whatsapp_number']
    sms_phone = result['phone']

    # Determine which platform
    if telegram_num == phone_number:
        platform = "Telegram"
    elif whatsapp_num == phone_number:
        platform = "WhatsApp"
    else:
        platform = "SMS"

    return {
        "user_id": str(user_id),
        "platform": platform
    }

def link_whatsapp_to_existing(user_id: str, whatsapp_number: str, chat_id: str) -> str:
    """
    Link WhatsApp number and chat_id to existing account.
    """
    cur = conn.cursor()
    cur.execute("""
        UPDATE users
        SET whatsapp_number = %s, whatsapp_chat_id = %s, updated_at = NOW()
        WHERE id = %s
    """, (whatsapp_number, chat_id, user_id))
    conn.commit()
    cur.close()
    return user_id

def link_telegram_to_account(phone: str, telegram_id: str) -> dict:
    """Legacy: immediately link Telegram to an account by phone. No verification."""
    user = get_user_by_phone(phone)
    if not user:
        return {"status": "error", "message": "No account found"}
    cur = conn.cursor()
    cur.execute("UPDATE users SET telegram_id = %s WHERE id = %s", (telegram_id, user['id']))
    conn.commit()
    cur.close()
    return {"status": "ok", "name": user['name']}


import random
from datetime import datetime, timedelta, timezone


def find_whatsapp_user_by_number(phone: str) -> dict:
    """
    Look up a user by their whatsapp_number column.
    Returns user info if found and has a whatsapp_chat_id.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, whatsapp_chat_id, created_at, user_id
        FROM users
        WHERE whatsapp_number = %s
    """, (phone,))
    row = cur.fetchone()
    cur.close()

    if not row:
        return None  # No account with this WhatsApp number

    user_id = row['id']
    name = row['name']
    chat_id = row['whatsapp_chat_id']
    created_at = row['created_at']
    if not chat_id:
        return {"status": "no_chat_id", "id": str(user_id), "name": name}

    return {
        "status": "ok",
        "id": str(user_id),
        "name": name,
        "whatsapp_chat_id": chat_id,
        "created_at": created_at
    }


def generate_linking_code(user_id: str) -> str:
    """
    Generate a 6-digit verification code, store it and expiry on the user row.
    Returns the generated code.
    """
    code = str(random.randint(100000, 999999))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    cur = conn.cursor()
    cur.execute("""
        UPDATE users
        SET linking_code = %s, code_expire_at = %s, updated_at = NOW()
        WHERE id = %s
    """, (code, expires_at, user_id))
    conn.commit()
    cur.close()

    return code


def verify_linking_code(phone: str, entered_code: str) -> dict:
    """
    Verify the linking code for a WhatsApp user.
    Returns the user row on success, error dict on failure.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, linking_code, code_expire_at, created_at, user_id
        FROM users
        WHERE whatsapp_number = %s OR telegram_number = %s OR phone = %s
    """, (phone, phone, phone))
    row = cur.fetchone()
    cur.close()

    if not row:
        return {"status": "error", "message": "No account found with that number"}

    user_id = row['id']
    name = row['name']
    stored_code = row['linking_code']
    expires_at = row['code_expire_at']
    created_at = row['created_at']

    if not stored_code:
        return {"status": "error", "message": "No verification code was sent. Please start the linking process again."}

    if expires_at and expires_at < datetime.now(timezone.utc):
        return {"status": "error", "message": "❌ Verification code has expired. Please start linking again."}

    if stored_code != entered_code:
        return {"status": "error", "message": "❌ Incorrect code. Please try again."}

    # Clear the code fields
    cur = conn.cursor()
    cur.execute("""
        UPDATE users SET linking_code = NULL, code_expire_at = NULL, updated_at = NOW()
        WHERE id = %s
    """, (user_id,))
    conn.commit()
    cur.close()

    return {
        "status": "ok",
        "id": str(user_id),
        "name": name,
        "created_at": created_at
    }


def _merge_accounts(keep_id: str, merge_from_id: str) -> dict:
    """
    Merge data from merge_from account into keep account.

    1. Update FK references from merge_from_id to keep_id
    2. Delete the merge_from account
    """
    cur = conn.cursor()

    # Tables that reference users.id
    for table in ("listings", "listing_interests", "conversation_state",
                  "message_logs", "assistant_logs"):
        cur.execute(
            f"UPDATE {table} SET user_id = %s WHERE user_id = %s",
            (keep_id, merge_from_id)
        )

    # Delete the merged-from account
    cur.execute("DELETE FROM users WHERE id = %s", (merge_from_id,))

    conn.commit()
    cur.close()
    return {"status": "ok"}


def link_and_merge_accounts(whatsapp_user_id: str, telegram_id: str, telegram_number: str = None,
                            telegram_user_id_to_merge: str = None) -> dict:
    """
    Complete the linking process:
    1. Set telegram_id/telegram_number on the WhatsApp account
    2. If there's a separate Telegram user account, merge it into the WhatsApp account
       (keep the older account's ID)
    """
    cur = conn.cursor()

    if telegram_user_id_to_merge and telegram_user_id_to_merge != whatsapp_user_id:
        # Determine which account is older
        cur.execute("""
            SELECT id, created_at FROM users WHERE id IN (%s, %s)
        """ % ('%s', '%s'), (whatsapp_user_id, telegram_user_id_to_merge))
        rows = cur.fetchall()

        if len(rows) == 2:
            id_a, created_a = rows[0]['id'], rows[0]['created_at']
            id_b, created_b = rows[1]['id'], rows[1]['created_at']
            id_a, id_b = str(id_a), str(id_b)

            keep_id = id_a if created_a <= created_b else id_b
            merge_id = id_b if keep_id == id_a else id_a

            _merge_accounts(keep_id, merge_id)
            whatsapp_user_id = keep_id  # the surviving ID

    # Set telegram_id and telegram_number on the surviving account
    if telegram_number:
        cur.execute("""
            UPDATE users
            SET telegram_id = %s, telegram_number = %s, updated_at = NOW()
            WHERE id = %s
        """, (telegram_id, telegram_number, whatsapp_user_id))
    else:
        cur.execute("""
            UPDATE users
            SET telegram_id = %s, updated_at = NOW()
            WHERE id = %s
        """, (telegram_id, whatsapp_user_id))

    conn.commit()
    cur.close()

    return {"status": "ok", "user_id": whatsapp_user_id}

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

    verified = result['verified']
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

    verified = result['verified']
    role = result['role']
    pic_folder = result['pic_folder']

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