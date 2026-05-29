from db.connect import conn
from datetime import datetime, timedelta

def save_interest(listing_id: int, user_id: str, quantity: int = None, message: str = None) -> dict:
    """
    Save a user's interest in a listing.

    Args:
        listing_id: ID of the listing
        user_id: ID of the interested user
        quantity: Optional quantity (kg) user is interested in
        message: Optional message to seller

    Returns:
        dict with status, buyer info (for farmer notification), and listing info
    """
    cur = conn.cursor()

    # Get listing and seller information (both WhatsApp and Telegram)
    cur.execute("""
        SELECT l.*, c.name as crop_name, u.name as seller_name,
               u.whatsapp_chat_id as seller_whatsapp_chat_id,
               u.telegram_id as seller_telegram_id
        FROM listings l
        JOIN crops c ON l.crop_id = c.id
        JOIN users u ON l.user_id = u.id
        WHERE l.id = %s AND u.verified = 'true'
    """, (listing_id,))

    listing_data = cur.fetchone()

    if not listing_data:
        cur.close()
        return {"status": "error", "message": "Listing not found or no longer available"}

    # Check if user is trying to show interest in their own listing
    if str(listing_data[1]) == str(user_id):  # user_id column
        cur.close()
        return {"status": "error", "message": "You cannot show interest in your own listing"}

    # Get buyer information for notification
    cur.execute("""
        SELECT name, phone, whatsapp_chat_id
        FROM users
        WHERE id = %s
    """, (user_id,))
    buyer_info = cur.fetchone()

    # Check if active interest already exists
    cur.execute("""
        SELECT id FROM listing_interests
        WHERE listing_id = %s AND user_id = %s AND status = 'active'
    """, (listing_id, user_id))

    existing_interest = cur.fetchone()

    try:
        if existing_interest:
            # Update existing active interest
            cur.execute("""
                UPDATE listing_interests
                SET interested_quantity_kg = %s, message = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING id
            """, (quantity, message, existing_interest[0]))
            interest_id = cur.fetchone()[0]
        else:
            # Insert new interest
            cur.execute("""
                INSERT INTO listing_interests (listing_id, user_id, interested_quantity_kg, message, status)
                VALUES (%s, %s, %s, %s, 'active')
                RETURNING id
            """, (listing_id, user_id, quantity, message))
            interest_id = cur.fetchone()[0]

        conn.commit()
        cur.close()

        return {
            "status": "ok",
            "interest_id": interest_id,
            "listing": {
                "id": listing_data[0],
                "crop_name": listing_data[12],  # crop_name from join
                "quantity_kg": listing_data[3],
                "price": listing_data[4],
                "seller_name": listing_data[13],  # seller_name from join
            },
            "buyer": {
                "name": buyer_info[0],
                "phone": buyer_info[1],
            },
            "seller_notification": {
                "seller_whatsapp_chat_id": listing_data[14],  # seller_whatsapp_chat_id from join
                "seller_telegram_id": listing_data[15],  # seller_telegram_id from join
                "buyer_name": buyer_info[0],
                "buyer_phone": buyer_info[1],
                "crop_name": listing_data[12],
                "quantity": quantity,
            }
        }
    except Exception as e:
        conn.rollback()
        cur.close()
        print(f"SAVE INTEREST ERROR: {e}")
        return {"status": "error", "message": "Failed to save interest. Please try again."}

def get_listing_interests(user_id: str, crop_name: str = None) -> dict:
    """
    Get active interests shown on a farmer's listings (last 3 months).

    Args:
        user_id: Farmer's user ID
        crop_name: Optional filter by crop name

    Returns:
        dict with interests grouped by listing
    """
    cur = conn.cursor()

    filters = ["l.user_id = %s", "li.status = 'active'", "li.created_at >= NOW() - INTERVAL '3 months'"]
    values = [user_id]

    if crop_name:
        from db.controller.cropController import get_crop_id
        crop_id = get_crop_id(crop_name)
        if crop_id:
            filters.append("l.crop_id = %s")
            values.append(crop_id)

    where_clause = " AND ".join(filters)

    cur.execute(f"""
        SELECT
            li.id,
            l.id as listing_id,
            c.name as crop_name,
            l.quantity_kg,
            l.price,
            li.interested_quantity_kg,
            li.message,
            u.name as buyer_name,
            u.phone as buyer_phone,
            li.created_at,
            li.status
        FROM listing_interests li
        JOIN listings l ON li.listing_id = l.id
        JOIN crops c ON l.crop_id = c.id
        JOIN users u ON li.user_id = u.id
        WHERE {where_clause}
        ORDER BY li.created_at DESC
    """, values)

    interests = cur.fetchall()
    cur.close()

    if not interests:
        return {
            "status": "ok",
            "total": 0,
            "message": "No one has shown interest in your listings yet."
        }

    # Group by listing
    grouped = {}
    for interest in interests:
        listing_id = interest[1]
        if listing_id not in grouped:
            grouped[listing_id] = {
                "crop_name": interest[2],
                "quantity_kg": interest[3],
                "price": interest[4],
                "interests": []
            }

        grouped[listing_id]["interests"].append({
            "interest_id": interest[0],
            "quantity": interest[5],
            "message": interest[6],
            "buyer_name": interest[7],
            "buyer_phone": interest[8],
            "created_at": interest[9],
            "status": interest[10]
        })

    return {
        "status": "ok",
        "total": len(interests),
        "listings": grouped
    }

def get_user_interests(user_id: str) -> dict:
    """
    Get all active interests a user has shown (buyer's view, last 3 months).

    Args:
        user_id: Buyer's user ID

    Returns:
        dict with user's interests
    """
    cur = conn.cursor()

    cur.execute("""
        SELECT
            li.id,
            l.id as listing_id,
            c.name as crop_name,
            l.quantity_kg,
            l.price,
            li.interested_quantity_kg,
            li.message,
            u.name as seller_name,
            li.created_at,
            li.status
        FROM listing_interests li
        JOIN listings l ON li.listing_id = l.id
        JOIN crops c ON l.crop_id = c.id
        JOIN users u ON l.user_id = u.id
        WHERE li.user_id = %s
          AND li.status = 'active'
          AND li.created_at >= NOW() - INTERVAL '3 months'
        ORDER BY li.created_at DESC
    """, (user_id,))

    interests = cur.fetchall()
    cur.close()

    if not interests:
        return {
            "status": "ok",
            "total": 0,
            "message": "You haven't shown interest in any listings yet."
        }

    formatted_interests = []
    for interest in interests:
        formatted_interests.append({
            "interest_id": interest[0],
            "listing_id": interest[1],
            "crop_name": interest[2],
            "listing_quantity": interest[3],
            "price": interest[4],
            "interested_quantity": interest[5],
            "message": interest[6],
            "seller_name": interest[7],
            "created_at": interest[8],
            "status": interest[9]
        })

    return {
        "status": "ok",
        "total": len(interests),
        "interests": formatted_interests
    }

def cancel_interest(interest_id: int, user_id: str) -> dict:
    """
    Cancel an interest (buyer cancels their own interest).

    Args:
        interest_id: ID of the interest
        user_id: ID of the buyer (to verify ownership)

    Returns:
        dict with status and farmer notification data
    """
    cur = conn.cursor()

    # Get interest and verify ownership
    cur.execute("""
        SELECT li.id, li.listing_id, li.user_id, li.status,
               l.user_id as farmer_id, c.name as crop_name,
               u.whatsapp_chat_id as farmer_chat_id, u.name as farmer_name,
               buyer.name as buyer_name
        FROM listing_interests li
        JOIN listings l ON li.listing_id = l.id
        JOIN crops c ON l.crop_id = c.id
        JOIN users u ON l.user_id = u.id
        JOIN users buyer ON li.user_id = buyer.id
        WHERE li.id = %s
    """, (interest_id,))

    interest_data = cur.fetchone()

    if not interest_data:
        cur.close()
        return {"status": "error", "message": "Interest not found"}

    if str(interest_data[2]) != str(user_id):
        cur.close()
        return {"status": "error", "message": "You can only cancel your own interests"}

    if interest_data[3] != 'active':
        cur.close()
        return {"status": "error", "message": "This interest is already cancelled or rejected"}

    # Update status to cancelled_by_buyer
    try:
        cur.execute("""
            UPDATE listing_interests
            SET status = 'cancelled_by_buyer', updated_at = NOW()
            WHERE id = %s
        """, (interest_id,))
        conn.commit()
        cur.close()

        return {
            "status": "ok",
            "message": f"Interest in {interest_data[5]} cancelled successfully",
            "farmer_notification": {
                "farmer_chat_id": interest_data[6],
                "buyer_name": interest_data[8],
                "crop_name": interest_data[5],
            }
        }
    except Exception as e:
        conn.rollback()
        cur.close()
        print(f"CANCEL INTEREST ERROR: {e}")
        return {"status": "error", "message": "Failed to cancel interest"}

def reject_interest(interest_id: int, farmer_id: str) -> dict:
    """
    Reject an interest (farmer rejects a buyer's interest).

    Args:
        interest_id: ID of the interest
        farmer_id: ID of the farmer (to verify ownership of listing)

    Returns:
        dict with status and buyer notification data
    """
    cur = conn.cursor()

    # Get interest and verify farmer owns the listing
    cur.execute("""
        SELECT li.id, li.listing_id, li.user_id, li.status,
               l.user_id as farmer_id, c.name as crop_name,
               u.whatsapp_chat_id as buyer_chat_id, u.name as buyer_name,
               farmer.name as farmer_name
        FROM listing_interests li
        JOIN listings l ON li.listing_id = l.id
        JOIN crops c ON l.crop_id = c.id
        JOIN users u ON li.user_id = u.id
        JOIN users farmer ON l.user_id = farmer.id
        WHERE li.id = %s
    """, (interest_id,))

    interest_data = cur.fetchone()

    if not interest_data:
        cur.close()
        return {"status": "error", "message": "Interest not found"}

    if str(interest_data[4]) != str(farmer_id):
        cur.close()
        return {"status": "error", "message": "You can only reject interests on your own listings"}

    if interest_data[3] != 'active':
        cur.close()
        return {"status": "error", "message": "This interest is already cancelled or rejected"}

    # Update status to rejected_by_farmer
    try:
        cur.execute("""
            UPDATE listing_interests
            SET status = 'rejected_by_farmer', updated_at = NOW()
            WHERE id = %s
        """, (interest_id,))
        conn.commit()
        cur.close()

        return {
            "status": "ok",
            "message": f"Interest from {interest_data[7]} rejected",
            "buyer_notification": {
                "buyer_chat_id": interest_data[6],
                "farmer_name": interest_data[8],
                "crop_name": interest_data[5],
            }
        }
    except Exception as e:
        conn.rollback()
        cur.close()
        print(f"REJECT INTEREST ERROR: {e}")
        return {"status": "error", "message": "Failed to reject interest"}
