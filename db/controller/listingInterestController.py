from db.connect import conn


def save_interest(listing_id: int, user_id: str, quantity: int = None, message: str = None) -> dict:
    """
    Save a user's interest in a listing.

    Args:
        listing_id: ID of the listing
        user_id: ID of the interested user
        quantity: Optional quantity user is interested in
        message: Optional message to seller

    Returns:
        dict with status, buyer info (for farmer notification), and listing info
    """
    cur = conn.cursor()

    cur.execute("""
        SELECT l.id, l.user_id, l.product_id, l.quantity, l.measurement, l.price,
               loc.town, loc.region, l.origin, l.image_url,
               l.expires_at, l.created_at, l.updated_at,
               p.name as product_name, u.name as seller_name,
               u.whatsapp_chat_id as seller_whatsapp_chat_id,
               u.telegram_id as seller_telegram_id
        FROM listings l
        JOIN products p ON l.product_id = p.id
        JOIN users u ON l.user_id = u.id
        LEFT JOIN locations loc ON l.location_id = loc.id
        WHERE l.id = %s AND u.verified = 'true'
    """, (listing_id,))

    listing_data = cur.fetchone()

    if not listing_data:
        cur.close()
        return {"status": "error", "message": "Listing not found or no longer available"}

    # user_id column is at index 1
    if str(listing_data[1]) == str(user_id):
        cur.close()
        return {"status": "error", "message": "You cannot show interest in your own listing"}

    cur.execute("""
        SELECT name, phone, whatsapp_chat_id
        FROM users
        WHERE id = %s
    """, (user_id,))
    buyer_info = cur.fetchone()

    cur.execute("""
        SELECT id FROM listing_interests
        WHERE listing_id = %s AND user_id = %s AND status = 'active'
    """, (listing_id, user_id))

    existing_interest = cur.fetchone()

    try:
        if existing_interest:
            cur.execute("""
                UPDATE listing_interests
                SET interested_quantity_kg = %s, message = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING id
            """, (quantity, message, existing_interest[0]))
            interest_id = cur.fetchone()[0]
        else:
            cur.execute("""
                INSERT INTO listing_interests (listing_id, user_id, interested_quantity_kg, message, status)
                VALUES (%s, %s, %s, %s, 'active')
                RETURNING id
            """, (listing_id, user_id, quantity, message))
            interest_id = cur.fetchone()[0]

        conn.commit()
        cur.close()

        # Column indices: id=0, user_id=1, product_id=2, quantity=3, measurement=4,
        #                   price=5, town=6, region=7, origin=8, image_url=9,
        #                   expires_at=10, created_at=11, updated_at=12
        #                   product_name=13, seller_name=14, seller_whatsapp_chat_id=15, seller_telegram_id=16
        return {
            "status": "ok",
            "interest_id": interest_id,
            "listing": {
                "id": listing_data[0],
                "product_name": listing_data[13],
                "quantity": listing_data[3],
                "measurement": listing_data[4],
                "price": listing_data[5],
                "seller_name": listing_data[14],
            },
            "buyer": {
                "name": buyer_info[0],
                "phone": buyer_info[1],
            },
            "seller_notification": {
                "seller_whatsapp_chat_id": listing_data[15],
                "seller_telegram_id": listing_data[16],
                "buyer_name": buyer_info[0],
                "buyer_phone": buyer_info[1],
                "product_name": listing_data[13],
                "quantity": quantity,
            },
        }
    except Exception as e:
        conn.rollback()
        cur.close()
        print(f"SAVE INTEREST ERROR: {e}")
        return {"status": "error", "message": "Failed to save interest. Please try again."}


def get_listing_interests(user_id: str, product_name: str = None) -> dict:
    """
    Get active interests shown on a farmer's listings (last 3 months).

    Args:
        user_id: Farmer's user ID
        product_name: Optional filter by product name

    Returns:
        dict with interests grouped by listing
    """
    cur = conn.cursor()

    filters = ["l.user_id = %s", "li.status = 'active'", "li.created_at >= NOW() - INTERVAL '3 months'"]
    values = [user_id]

    if product_name:
        from db.controller.productController import get_product_id
        product_id = get_product_id(product_name)
        if product_id:
            filters.append("l.product_id = %s")
            values.append(product_id)

    where_clause = " AND ".join(filters)

    cur.execute(f"""
        SELECT
            li.id,
            l.id as listing_id,
            p.name as product_name,
            l.quantity,
            l.price,
            li.interested_quantity_kg,
            li.message,
            u.name as buyer_name,
            u.phone as buyer_phone,
            li.created_at,
            li.status
        FROM listing_interests li
        JOIN listings l ON li.listing_id = l.id
        JOIN products p ON l.product_id = p.id
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
            "message": "No one has shown interest in your listings yet.",
        }

    grouped = {}
    for interest in interests:
        listing_id = interest[1]
        if listing_id not in grouped:
            grouped[listing_id] = {
                "product_name": interest[2],
                "quantity": interest[3],
                "price": interest[4],
                "interests": [],
            }

        grouped[listing_id]["interests"].append({
            "interest_id": interest[0],
            "quantity": interest[5],
            "message": interest[6],
            "buyer_name": interest[7],
            "buyer_phone": interest[8],
            "created_at": interest[9],
            "status": interest[10],
        })

    return {
        "status": "ok",
        "total": len(interests),
        "listings": grouped,
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
            p.name as product_name,
            l.quantity,
            l.price,
            li.interested_quantity_kg,
            li.message,
            u.name as seller_name,
            li.created_at,
            li.status
        FROM listing_interests li
        JOIN listings l ON li.listing_id = l.id
        JOIN products p ON l.product_id = p.id
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
            "message": "You haven't shown interest in any listings yet.",
        }

    formatted_interests = []
    for interest in interests:
        formatted_interests.append({
            "interest_id": interest[0],
            "listing_id": interest[1],
            "product_name": interest[2],
            "listing_quantity": interest[3],
            "price": interest[4],
            "interested_quantity": interest[5],
            "message": interest[6],
            "seller_name": interest[7],
            "created_at": interest[8],
            "status": interest[9],
        })

    return {
        "status": "ok",
        "total": len(interests),
        "interests": formatted_interests,
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

    cur.execute("""
        SELECT li.id, li.listing_id, li.user_id, li.status,
               l.user_id as farmer_id, p.name as product_name,
               u.whatsapp_chat_id as farmer_chat_id, u.name as farmer_name,
               buyer.name as buyer_name
        FROM listing_interests li
        JOIN listings l ON li.listing_id = l.id
        JOIN products p ON l.product_id = p.id
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
                "product_name": interest_data[5],
            },
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

    cur.execute("""
        SELECT li.id, li.listing_id, li.user_id, li.status,
               l.user_id as farmer_id, p.name as product_name,
               u.whatsapp_chat_id as buyer_chat_id, u.name as buyer_name,
               farmer.name as farmer_name
        FROM listing_interests li
        JOIN listings l ON li.listing_id = l.id
        JOIN products p ON l.product_id = p.id
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
                "product_name": interest_data[5],
            },
        }
    except Exception as e:
        conn.rollback()
        cur.close()
        print(f"REJECT INTEREST ERROR: {e}")
        return {"status": "error", "message": "Failed to reject interest"}
