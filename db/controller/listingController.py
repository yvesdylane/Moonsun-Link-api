from db.connect import conn
from db.controller.cropController import get_crop_id
from db.controller.userController import get_user_role

def create_listing(user_id, crop_name, quantity, price, town, region, image_url=None):
    crop_id = get_crop_id(crop_name)
    if not crop_id:
        return {"status": "error", "message": f"Crop '{crop_name}' not found"}

    cur = conn.cursor()
    query = """
        INSERT INTO listings (user_id, crop_id, quantity_kg, price, town, region, image_url)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    cur.execute(query, (user_id, crop_id, quantity, price, town, region, image_url))
    listing_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    return {"status": "ok", "listing_id": listing_id}


def delete_listing(listing_id: int, user_id: str):
    role = get_user_role(user_id)
    cur = conn.cursor()

    if role == "admin":
        cur.execute("DELETE FROM listings WHERE id = %s RETURNING id", (listing_id,))
    else:
        cur.execute("DELETE FROM listings WHERE id = %s AND user_id = %s RETURNING id", (listing_id, user_id))

    deleted = cur.fetchone()
    conn.commit()
    cur.close()

    if not deleted:
        return {"status": "error", "message": "Listing not found or not yours"}
    return {"status": "ok", "message": "Listing deleted"}


def update_listing(listing_id: int, user_id: str, updates: dict):
    if not updates:
        return {"status": "error", "message": "Nothing to update"}

    fields = [f"{key} = %s" for key in updates.keys()]
    values = list(updates.values())
    values.extend([listing_id, user_id])

    query = f"UPDATE listings SET {', '.join(fields)}, updated_at = NOW() WHERE id = %s AND user_id = %s RETURNING id"

    cur = conn.cursor()
    cur.execute(query, values)
    updated = cur.fetchone()
    conn.commit()
    cur.close()

    if not updated:
        return {"status": "error", "message": "Listing not found or not yours"}
    return {"status": "ok", "message": "Listing updated successfully"}

def get_listings(page=1, limit=10, crop_name=None, town=None, region=None, max_price=None, user_id=None, include_unverified=False):
    crop_id = get_crop_id(crop_name) if crop_name else None

    filters = []
    values = []

    if crop_id:
        filters.append("l.crop_id = %s")
        values.append(crop_id)
    if town:
        filters.append("l.town ILIKE %s")
        values.append(f"%{town}%")
    if region:
        filters.append("l.region = %s")
        values.append(region)
    if max_price:
        filters.append("l.price <= %s")
        values.append(max_price)
    if user_id:
        filters.append("l.user_id = %s")
        values.append(user_id)
    else:
        # Only show verified farmers' listings in public search
        if not include_unverified:
            filters.append("u.verified = 'true'")

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    offset = (page - 1) * limit

    cur = conn.cursor()

    # get total count
    cur.execute(f"""
        SELECT COUNT(*) 
        FROM listings l
        JOIN crops c ON l.crop_id = c.id
        JOIN users u ON l.user_id = u.id
        {where}
    """, values)
    total = cur.fetchone()[0]

    # get page
    cur.execute(f"""
        SELECT l.*, c.name as crop_name, u.name as seller_name
        FROM listings l
        JOIN crops c ON l.crop_id = c.id
        JOIN users u ON l.user_id = u.id
        {where}
        ORDER BY l.created_at DESC
        LIMIT %s OFFSET %s
    """, values + [limit, offset])

    listings = cur.fetchall()
    cur.close()

    total_pages = (total + limit - 1) // limit

    return {
        "listings": listings,
        "page": page,
        "total_pages": total_pages,
        "total": total
    }

def get_available_products() -> list:
    """
    Get list of distinct products currently being sold by verified farmers.

    Returns:
        List of product names
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT c.name
        FROM listings l
        JOIN crops c ON l.crop_id = c.id
        JOIN users u ON l.user_id = u.id
        WHERE u.verified = 'true'
        ORDER BY c.name
    """)
    products = [row[0] for row in cur.fetchall()]
    cur.close()
    return products

def get_product_locations(crop_name: str) -> dict:
    """
    Get regions and towns where a specific product is being sold by verified farmers.

    Args:
        crop_name: Name of the crop/product

    Returns:
        dict with status, product name, and location data
    """
    crop_id = get_crop_id(crop_name)
    if not crop_id:
        return {"status": "error", "message": f"Product '{crop_name}' not recognized"}

    cur = conn.cursor()

    # Check if product exists in verified listings
    cur.execute("""
        SELECT COUNT(*)
        FROM listings l
        JOIN users u ON l.user_id = u.id
        WHERE l.crop_id = %s AND u.verified = 'true'
    """, (crop_id,))

    count = cur.fetchone()[0]

    if count == 0:
        cur.close()
        return {
            "status": "not_found",
            "product": crop_name,
            "message": f"No one is currently selling {crop_name}"
        }

    # Get regions and towns
    cur.execute("""
        SELECT DISTINCT l.region, l.town
        FROM listings l
        JOIN users u ON l.user_id = u.id
        WHERE l.crop_id = %s AND u.verified = 'true'
        ORDER BY l.region, l.town
    """, (crop_id,))

    locations = cur.fetchall()
    cur.close()

    # Organize by region
    regions_data = {}
    for region, town in locations:
        if region not in regions_data:
            regions_data[region] = []
        if town and town not in regions_data[region]:
            regions_data[region].append(town)

    return {
        "status": "ok",
        "product": crop_name,
        "count": count,
        "regions": regions_data
    }

def check_product_exists(crop_name: str, region: str = None, max_price: int = None) -> dict:
    """
    Check if a product exists in verified listings and where it fails criteria.

    Args:
        crop_name: Name of the crop/product
        region: Optional region filter
        max_price: Optional maximum price filter

    Returns:
        dict with existence status and alternative suggestions
    """
    crop_id = get_crop_id(crop_name)
    if not crop_id:
        return {"exists": False, "reason": "unknown_product"}

    cur = conn.cursor()

    # Check if product exists at all in verified listings
    cur.execute("""
        SELECT COUNT(*)
        FROM listings l
        JOIN users u ON l.user_id = u.id
        WHERE l.crop_id = %s AND u.verified = 'true'
    """, (crop_id,))

    total_count = cur.fetchone()[0]

    if total_count == 0:
        cur.close()
        return {"exists": False, "reason": "not_listed"}

    # Check with filters
    filters = ["l.crop_id = %s", "u.verified = 'true'"]
    values = [crop_id]

    if region:
        filters.append("l.region = %s")
        values.append(region)

    if max_price:
        filters.append("l.price <= %s")
        values.append(max_price)

    where = " AND ".join(filters)

    cur.execute(f"""
        SELECT COUNT(*)
        FROM listings l
        JOIN users u ON l.user_id = u.id
        WHERE {where}
    """, values)

    filtered_count = cur.fetchone()[0]

    if filtered_count > 0:
        cur.close()
        return {"exists": True, "count": filtered_count}

    # Product exists but doesn't match criteria - provide feedback
    feedback = {"exists": True, "matches_criteria": False, "total_listings": total_count}

    # Check what's failing
    if region:
        cur.execute("""
            SELECT DISTINCT l.region
            FROM listings l
            JOIN users u ON l.user_id = u.id
            WHERE l.crop_id = %s AND u.verified = 'true'
        """, (crop_id,))
        available_regions = [row[0] for row in cur.fetchall()]
        feedback["available_regions"] = available_regions
        feedback["searched_region"] = region

    if max_price:
        cur.execute("""
            SELECT MIN(l.price)
            FROM listings l
            JOIN users u ON l.user_id = u.id
            WHERE l.crop_id = %s AND u.verified = 'true'
        """, (crop_id,))
        min_price = cur.fetchone()[0]
        feedback["min_price"] = min_price
        feedback["max_price_searched"] = max_price

    cur.close()
    return feedback

def search_by_price(crop_name: str, target_price: int, tolerance: int = 50) -> dict:
    """
    Search for listings at or near a specific price point.

    Args:
        crop_name: Name of the crop/product
        target_price: Desired price per kg
        tolerance: Price difference tolerance (default: 50 XAF)

    Returns:
        dict with exact matches or nearest alternatives
    """
    from db.controller.cropController import get_crop_id

    crop_id = get_crop_id(crop_name)
    if not crop_id:
        return {"status": "error", "message": f"Product '{crop_name}' not recognized"}

    cur = conn.cursor()

    # Check if product exists at all
    cur.execute("""
        SELECT COUNT(*)
        FROM listings l
        JOIN users u ON l.user_id = u.id
        WHERE l.crop_id = %s AND u.verified = 'true'
    """, (crop_id,))

    total_count = cur.fetchone()[0]

    if total_count == 0:
        cur.close()
        return {
            "status": "not_found",
            "message": f"No one is currently selling {crop_name}"
        }

    # Search for exact or close matches
    cur.execute("""
        SELECT l.*, c.name as crop_name, u.name as seller_name,
               ABS(l.price - %s) as price_diff
        FROM listings l
        JOIN crops c ON l.crop_id = c.id
        JOIN users u ON l.user_id = u.id
        WHERE l.crop_id = %s
          AND u.verified = 'true'
          AND l.price BETWEEN %s AND %s
        ORDER BY price_diff ASC, l.created_at DESC
        LIMIT 10
    """, (target_price, crop_id, target_price - tolerance, target_price + tolerance))

    close_matches = cur.fetchall()

    if close_matches:
        cur.close()
        return {
            "status": "ok",
            "match_type": "close",
            "target_price": target_price,
            "listings": close_matches,
            "message": f"Found {len(close_matches)} listing(s) near {target_price} XAF"
        }

    # No close matches - find nearest alternatives
    cur.execute("""
        SELECT l.price, COUNT(*) as count
        FROM listings l
        JOIN users u ON l.user_id = u.id
        WHERE l.crop_id = %s AND u.verified = 'true'
        GROUP BY l.price
        ORDER BY ABS(l.price - %s) ASC
        LIMIT 3
    """, (crop_id, target_price))

    nearest_prices = cur.fetchall()
    cur.close()

    return {
        "status": "alternatives",
        "target_price": target_price,
        "nearest_prices": [{"price": row[0], "count": row[1]} for row in nearest_prices],
        "message": f"No listings at {target_price} XAF, but here are the nearest prices"
    }