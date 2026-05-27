from db.connect import conn

def save_interest(listing_id: int, user_id: str, quantity: int, message: str = None) -> dict:
    """
    Save a user's interest in a listing.

    Args:
        listing_id: ID of the listing
        user_id: ID of the interested user
        quantity: Quantity (kg) user is interested in
        message: Optional message to seller

    Returns:
        dict with status and listing/seller information
    """
    cur = conn.cursor()

    # Get listing and seller information
    cur.execute("""
        SELECT l.*, c.name as crop_name, u.name as seller_name, u.phone, u.whatsapp_number
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

    # Save or update interest (UPSERT)
    try:
        cur.execute("""
            INSERT INTO listing_interests (listing_id, user_id, interested_quantity_kg, message)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (listing_id, user_id)
            DO UPDATE SET
                interested_quantity_kg = EXCLUDED.interested_quantity_kg,
                message = EXCLUDED.message,
                created_at = NOW()
            RETURNING id
        """, (listing_id, user_id, quantity if quantity else None, message))

        interest_id = cur.fetchone()[0]
        conn.commit()
        cur.close()

        return {
            "status": "ok",
            "interest_id": interest_id,
            "listing": {
                "id": listing_data[0],
                "crop_name": listing_data[-2],
                "quantity_kg": listing_data[3],
                "price": listing_data[4],
                "seller_name": listing_data[-1],
                "seller_phone": listing_data[-3],
                "seller_whatsapp": listing_data[-4]
            }
        }
    except Exception as e:
        conn.rollback()
        cur.close()
        print(f"SAVE INTEREST ERROR: {e}")
        return {"status": "error", "message": "Failed to save interest. Please try again."}

def get_listing_interests(user_id: str, crop_name: str = None) -> dict:
    """
    Get interests shown on a farmer's listings.

    Args:
        user_id: Farmer's user ID
        crop_name: Optional filter by crop name

    Returns:
        dict with interests grouped by listing
    """
    cur = conn.cursor()

    filters = ["l.user_id = %s"]
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
            li.created_at
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
            "created_at": interest[9]
        })

    return {
        "status": "ok",
        "total": len(interests),
        "listings": grouped
    }

def get_user_interests(user_id: str) -> dict:
    """
    Get all interests a user has shown (buyer's view).

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
            li.created_at
        FROM listing_interests li
        JOIN listings l ON li.listing_id = l.id
        JOIN crops c ON l.crop_id = c.id
        JOIN users u ON l.user_id = u.id
        WHERE li.user_id = %s
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
            "created_at": interest[8]
        })

    return {
        "status": "ok",
        "total": len(interests),
        "interests": formatted_interests
    }
