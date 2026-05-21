from db.connect import conn
from db.controller.cropController import get_crop_id
from db.controller.userController import get_user_role

def create_listing(user_id: str, crop_name: str, quantity: int, price: int, town: str, region: str):
    crop_id = get_crop_id(crop_name)
    if not crop_id:
        return {"status": "error", "message": f"Crop '{crop_name}' not found"}

    cur = conn.cursor()
    query = """
        INSERT INTO listings (user_id, crop_id, quantity_kg, price, town, region)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    cur.execute(query, (user_id, crop_id, quantity, price, town, region))
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


def update_listing(listing_id: int, user_id: str, quantity: int = None, price: int = None):
    fields = []
    values = []

    if quantity:
        fields.append("quantity_kg = %s")
        values.append(quantity)
    if price:
        fields.append("price = %s")
        values.append(price)

    if not fields:
        return {"status": "error", "message": "Nothing to update"}

    values.extend([listing_id, user_id])
    query = f"UPDATE listings SET {', '.join(fields)} WHERE id = %s AND user_id = %s RETURNING id"

    cur = conn.cursor()
    cur.execute(query, values)
    updated = cur.fetchone()
    conn.commit()
    cur.close()

    if not updated:
        return {"status": "error", "message": "Listing not found or not yours"}
    return {"status": "ok", "message": "Listing updated"}

def get_listings(page=1, limit=10, crop_name=None, town=None, region=None, max_price=None, user_id=None):
    crop_id = get_crop_id(crop_name) if crop_name else None

    filters = []
    values = []

    if crop_id:
        filters.append("crop_id = %s")
        values.append(crop_id)
    if town:
        filters.append("town ILIKE %s")
        values.append(f"%{town}%")
    if region:
        filters.append("region = %s")
        values.append(region)
    if max_price:
        filters.append("price <= %s")
        values.append(max_price)
    if user_id:
        filters.append("user_id = %s")
        values.append(user_id)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    offset = (page - 1) * limit
    values.extend([limit, offset])

    cur = conn.cursor()
    cur.execute(f"SELECT * FROM listings {where} LIMIT %s OFFSET %s", values)
    listings = cur.fetchall()
    cur.close()
    return listings
