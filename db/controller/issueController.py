from db.connect import conn


def create_issue(user_id: str, title: str, description: str = None,
                 product_name: str = None, issue_type: str = 'other',
                 location: str = None, region: str = None) -> dict:
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO issues (user_id, title, description, product_name, issue_type, location, region)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, created_at
        """, (user_id, title, description, product_name, issue_type, location, region))
        issue_id, created_at = cur.fetchone()
        conn.commit()
        return {
            "status": "ok",
            "issue_id": issue_id,
            "title": title,
            "issue_type": issue_type,
            "created_at": created_at,
        }
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": f"Failed to save issue: {e}"}
    finally:
        cur.close()


def get_issues(product_name: str = None, issue_type: str = None,
               region: str = None, status: str = 'open') -> list:
    filters = ["i.status = %s"]
    values = [status]

    if product_name:
        filters.append("i.product_name = %s")
        values.append(product_name)
    if issue_type:
        filters.append("i.issue_type = %s")
        values.append(issue_type)
    if region:
        filters.append("(i.region = %s OR i.region IS NULL)")
        values.append(region)

    where = " AND ".join(filters)

    cur = conn.cursor()
    cur.execute(f"""
        SELECT i.id, i.title, i.description, i.product_name, i.issue_type,
               i.location, i.region, i.created_at, u.name as author_name
        FROM issues i
        JOIN users u ON i.user_id = u.id
        WHERE {where}
        ORDER BY i.created_at DESC
    """, values)
    rows = cur.fetchall()
    cur.close()
    return rows


def get_issue_by_id(issue_id: int) -> tuple:
    cur = conn.cursor()
    cur.execute("""
        SELECT i.*, u.name as author_name
        FROM issues i
        JOIN users u ON i.user_id = u.id
        WHERE i.id = %s
    """, (issue_id,))
    row = cur.fetchone()
    cur.close()
    return row


def create_advice(issue_id: int, author_id: str, title: str, content: str,
                  product_name: str = None, issue_type: str = None) -> dict:
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO advice (issue_id, author_id, title, content, product_name, issue_type)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (issue_id, author_id, title, content, product_name, issue_type))
        advice_id = cur.fetchone()[0]
        conn.commit()
        return {"status": "ok", "advice_id": advice_id}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": f"Failed to save advice: {e}"}
    finally:
        cur.close()


def search_advice(product_name: str = None, issue_type: str = None) -> list:
    filters = []
    values = []

    if product_name:
        filters.append("a.product_name = %s")
        values.append(product_name)
    if issue_type:
        filters.append("a.issue_type = %s")
        values.append(issue_type)

    if not filters:
        return []

    where = " AND ".join(filters)

    cur = conn.cursor()
    cur.execute(f"""
        SELECT a.id, a.title, a.content, a.product_name, a.issue_type,
               a.is_verified, a.upvotes, u.name as author_name
        FROM advice a
        JOIN users u ON a.author_id = u.id
        WHERE {where}
        ORDER BY a.is_verified DESC, a.upvotes DESC
        LIMIT 3
    """, values)
    rows = cur.fetchall()
    cur.close()
    return rows


def get_advice_for_issue(issue_id: int) -> list:
    cur = conn.cursor()
    cur.execute("""
        SELECT a.id, a.title, a.content, a.is_verified, a.upvotes,
               u.name as author_name, a.created_at
        FROM advice a
        JOIN users u ON a.author_id = u.id
        WHERE a.issue_id = %s
        ORDER BY a.upvotes DESC, a.created_at DESC
    """, (issue_id,))
    rows = cur.fetchall()
    cur.close()
    return rows
