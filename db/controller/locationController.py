from db.connect import conn


def create_location(town: str, region: str, department: str = None) -> dict:
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO locations (town, department, region)
            VALUES (%s, %s, %s)
            RETURNING *
        """, (town, department, region))
        location = cur.fetchone()
        conn.commit()
        if not location:
            return {"status": "error", "message": "Failed to create location"}
        return {"status": "ok", "location": location}
    except Exception as e:
        conn.rollback()
        err = str(e)
        if "unique" in err.lower() or "duplicate" in err.lower():
            return {"status": "error", "message": f"Location '{town}' already exists in region '{region}'"}
        return {"status": "error", "message": err}
    finally:
        cur.close()


def get_location(location_id: int) -> dict | None:
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM locations WHERE id = %s", (location_id,))
        return cur.fetchone()
    finally:
        cur.close()


def get_all_locations(town: str = None, region: str = None) -> list[dict]:
    cur = conn.cursor()
    try:
        conditions = []
        params = []
        if town:
            conditions.append("LOWER(town) LIKE LOWER(%s)")
            params.append(f"%{town}%")
        if region:
            conditions.append("region = %s")
            params.append(region)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        cur.execute(f"""
            SELECT * FROM locations {where} ORDER BY region, town
        """, params)
        return cur.fetchall()
    finally:
        cur.close()


def update_location(location_id: int, updates: dict) -> dict:
    if not updates:
        return {"status": "error", "message": "Nothing to update"}

    fields = [f"{key} = %s" for key in updates.keys()]
    values = list(updates.values())
    values.append(location_id)

    cur = conn.cursor()
    try:
        cur.execute(f"""
            UPDATE locations
            SET {', '.join(fields)}
            WHERE id = %s
            RETURNING *
        """, values)
        updated = cur.fetchone()
        conn.commit()
        if not updated:
            return {"status": "error", "message": "Location not found"}
        return {"status": "ok", "location": updated}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        cur.close()


def delete_location(location_id: int) -> dict:
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) AS cnt FROM listings WHERE location_id = %s", (location_id,))
        count = cur.fetchone()["cnt"]
        if count > 0:
            return {
                "status": "error",
                "message": f"Cannot delete: {count} listing(s) still use this location. Reassign them first."
            }

        cur.execute("DELETE FROM locations WHERE id = %s RETURNING id", (location_id,))
        deleted = cur.fetchone()
        conn.commit()
        if not deleted:
            return {"status": "error", "message": "Location not found"}
        return {"status": "ok", "message": "Location deleted"}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        cur.close()
