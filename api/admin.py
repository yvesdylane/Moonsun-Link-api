from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
import traceback

from utils.admin_auth import create_token, get_current_admin, send_admin_code
from db.controller.adminController import (
    get_all_users, get_all_listings, get_dashboard_stats,
    get_pending_verifications, approve_verification, reject_verification,
    update_report_status, update_issue_status,
)
from db.controller.userController import (
    get_user_by_phone, generate_linking_code, verify_linking_code,
    get_user_info, update_user_info,
)
from db.controller.listingController import delete_listing, get_listing_details as _get_listing_details
from db.controller.reportController import get_reports
from db.controller.issueController import get_issues
from db.controller.alertController import create_alert as _create_alert, get_all_user_contacts, get_alerts as _get_alerts
from db.controller.listingInterestController import get_all_interests as _get_all_interests
from db.controller.messageLogController import (
    get_message_logs as _get_message_logs,
    get_message_log as _get_message_log,
)
from db.controller.logController import (
    get_assistant_logs as _get_assistant_logs,
    get_assistant_log as _get_assistant_log,
)
from db.controller.stateController import (
    get_all_conversation_states as _get_all_conversation_states,
    get_conversation_state_detail as _get_conversation_state_detail,
)
from db.controller.locationController import (
    create_location as _create_location,
    get_location as _get_location,
    get_all_locations as _get_all_locations,
    update_location as _update_location,
    delete_location as _delete_location,
)
from db.controller.adviceController import (
    create_advice as _create_advice,
    get_advice as _get_advice,
    get_all_advice as _get_all_advice,
    update_advice as _update_advice,
    delete_advice as _delete_advice,
)
from db.controller.productController import (
    create_product as _create_product,
    get_all_products as _get_all_products,
    get_product_info as _get_product_info,
    update_product as _update_product,
    delete_product as _delete_product,
)
from db.connect import conn as _db_conn
from db.controller.productPriceController import (
    create_product_price as _create_product_price,
    get_product_prices as _get_product_prices,
    update_product_price as _update_product_price,
    delete_product_price as _delete_product_price,
)

router = APIRouter(tags=["Admin"])


class LoginRequest(BaseModel):
    phone: str


class VerifyRequest(BaseModel):
    phone: str
    code: str


class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    verified: Optional[str] = None
    region: Optional[str] = None


class UpdateReportRequest(BaseModel):
    status: str


class UpdateIssueRequest(BaseModel):
    status: str


class CreateAlertRequest(BaseModel):
    title: str
    description: Optional[str] = None
    alert_type: str
    region: Optional[str] = None
    product_name: Optional[str] = None
    source_report_id: Optional[int] = None
    expires_at: Optional[str] = None


class CreateAdviceRequest(BaseModel):
    title: str
    content: str
    issue_id: Optional[int] = None
    product_name: Optional[str] = None
    issue_type: Optional[str] = None
    is_verified: bool = False


class UpdateAdviceRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    issue_id: Optional[int] = None
    product_name: Optional[str] = None
    issue_type: Optional[str] = None
    is_verified: Optional[bool] = None


class CreateProductRequest(BaseModel):
    name: str
    type: str
    default_measurement: Optional[str] = None


class UpdateProductRequest(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    default_measurement: Optional[str] = None


class CreateProductPriceRequest(BaseModel):
    product_id: int
    region: str
    min_price: int
    max_price: int
    avg_price: int


class UpdateProductPriceRequest(BaseModel):
    region: Optional[str] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    avg_price: Optional[int] = None


class CreateLocationRequest(BaseModel):
    town: str
    region: str
    department: Optional[str] = None


class UpdateLocationRequest(BaseModel):
    town: Optional[str] = None
    region: Optional[str] = None
    department: Optional[str] = None


# ── Auth ────────────────────────────────────────────────────────────────

@router.post("/login")
def admin_login(body: LoginRequest):
    try:
        phone = body.phone.strip()
        if not phone.startswith("+237"):
            phone = "+237" + phone

        user = get_user_by_phone(phone)
        if not user:
            raise HTTPException(status_code=404, detail="No account found with that phone number")

        from db.models.user import User
        u = User.from_db_row(user)
        if not u or not u.is_admin():
            raise HTTPException(status_code=403, detail="Admin privileges required")

        user_id = str(u.id)
        code = generate_linking_code(user_id)
        send_admin_code(phone, code, user)

        return {
            "status": "ok",
            "message": "Verification code sent to your WhatsApp and/or Telegram",
            "phone": phone,
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN LOGIN ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/verify")
def admin_verify(body: VerifyRequest):
    try:
        phone = body.phone.strip()
        if not phone.startswith("+237"):
            phone = "+237" + phone

        result = verify_linking_code(phone, body.code.strip())
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])

        user_id = result["id"]
        user = get_user_info(user_id)
        if not user or not user.is_admin():
            raise HTTPException(status_code=403, detail="Admin privileges required")

        token = create_token(str(user.id))
        return {
            "status": "ok",
            "token": token,
            "user": {
                "id": str(user.id),
                "name": user.name,
                "role": user.role,
                "phone": user.phone,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN VERIFY ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Stats ───────────────────────────────────────────────────────────────

@router.get("/stats")
def admin_stats(_auth=Depends(get_current_admin)):
    try:
        stats = get_dashboard_stats()
        return {"status": "ok", "data": stats}
    except Exception as e:
        print(f"ADMIN STATS ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Users ───────────────────────────────────────────────────────────────

@router.get("/users")
def admin_list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    role: Optional[str] = None,
    verified: Optional[str] = None,
    region: Optional[str] = None,
    search: Optional[str] = None,
    _auth=Depends(get_current_admin),
):
    try:
        result = get_all_users(
            page=page, limit=limit,
            role=role, verified=verified,
            region=region, search=search,
        )
        return {"status": "ok", "data": result}
    except Exception as e:
        print(f"ADMIN LIST USERS ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/users/{user_id}")
def admin_get_user(user_id: str, _auth=Depends(get_current_admin)):
    try:
        user = get_user_info(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {"status": "ok", "data": vars(user)}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN GET USER ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/users/{user_id}")
def admin_update_user(user_id: str, body: UpdateUserRequest, _auth=Depends(get_current_admin)):
    try:
        updates = {}
        verified_changed = False
        new_verified = None
        if body.name is not None:
            updates["name"] = body.name
        if body.role is not None:
            valid_roles = ("buyer", "farmer", "admin")
            if body.role not in valid_roles:
                raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}")
            updates["role"] = body.role
        if body.verified is not None:
            valid_ver = ("true", "false", "pending")
            if body.verified not in valid_ver:
                raise HTTPException(status_code=400, detail=f"Invalid verified value. Must be one of: {', '.join(valid_ver)}")
            updates["verified"] = body.verified
            verified_changed = True
            new_verified = body.verified
        if body.region is not None:
            updates["region"] = body.region

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = update_user_info(user_id, updates)
        if result["status"] == "error":
            raise HTTPException(status_code=404, detail=result["message"])

        user = result.get("user")

        if verified_changed and new_verified in ("true", "false"):
            from utils.whatsapp import send_whatsapp_reply
            if new_verified == "true":
                notification = (
                    "✅ *Account Verified!*\n\n"
                    "Your Moonso Link account has been verified. "
                    "Your listings are now visible to all buyers! 🎉"
                )
            else:
                notification = (
                    "❌ *Verification Revoked*\n\n"
                    "Your account verification status has been changed to not verified. "
                    "If you believe this is an error, please contact support."
                )
            whatsapp_chat_id = user.get("whatsapp_chat_id")
            telegram_id = user.get("telegram_id")
            if whatsapp_chat_id:
                try:
                    send_whatsapp_reply(whatsapp_chat_id, notification)
                except Exception as e:
                    print(f"ADMIN PATCH VERIFY WHATSAPP NOTIFY ERROR: {e}")
            if telegram_id:
                try:
                    import os
                    import requests
                    tg_token = os.getenv("TELEGRAM_TOKEN")
                    if tg_token:
                        requests.post(
                            f"https://api.telegram.org/bot{tg_token}/sendMessage",
                            json={"chat_id": telegram_id, "text": notification, "parse_mode": "Markdown"},
                            timeout=10,
                        )
                except Exception as e:
                    print(f"ADMIN PATCH VERIFY TELEGRAM NOTIFY ERROR: {e}")

        return {"status": "ok", "message": "User updated", "data": user}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN UPDATE USER ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Listings ────────────────────────────────────────────────────────────

@router.get("/listings")
def admin_list_listings(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    product_name: Optional[str] = None,
    region: Optional[str] = None,
    verified_only: bool = False,
    _auth=Depends(get_current_admin),
):
    try:
        result = get_all_listings(
            page=page, limit=limit,
            product_name=product_name,
            region=region,
            verified_only=verified_only,
        )
        return {"status": "ok", "data": result}
    except Exception as e:
        print(f"ADMIN LIST LISTINGS ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/listings/{listing_id}")
def admin_get_listing(listing_id: int, _auth=Depends(get_current_admin)):
    try:
        details = _get_listing_details(listing_id)
        if not details or details.get("status") == "error":
            raise HTTPException(status_code=404, detail="Listing not found")
        return {"status": "ok", "data": details}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN GET LISTING ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/listings/{listing_id}")
def admin_delete_listing(listing_id: int, _auth=Depends(get_current_admin)):
    try:
        # Admin bypass: pass admin's user_id so delete_listing uses the admin role check
        from db.controller.userController import get_user_info, get_user_role
        _auth_user_id, _auth_user = _auth
        result = delete_listing(listing_id=listing_id, user_id=_auth_user_id)
        if result["status"] == "error":
            raise HTTPException(status_code=404, detail=result["message"])
        return {"status": "ok", "message": "Listing deleted"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN DELETE LISTING ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Listing Interests ───────────────────────────────────────────────────


@router.get("/interests")
def admin_list_interests(
    status: Optional[str] = Query(None),
    listing_id: Optional[int] = Query(None),
    user_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _auth=Depends(get_current_admin),
):
    try:
        valid_statuses = ("active", "cancelled_by_buyer", "rejected_by_farmer")
        if status and status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            )
        all_items = _get_all_interests(status=status, listing_id=listing_id, user_id=user_id)
        total = len(all_items)
        total_pages = max(1, -(-total // limit)) if total else 1
        offset = (page - 1) * limit
        items = all_items[offset:offset + limit]
        return {
            "status": "ok",
            "data": {
                "total": total,
                "page": page,
                "limit": limit,
                "total_pages": total_pages,
                "interests": items,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN LIST INTERESTS ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/interests/{interest_id}")
def admin_get_interest(interest_id: int, _auth=Depends(get_current_admin)):
    try:
        cur = _db_conn.cursor()
        cur.execute("""
            SELECT li.*, p.name AS product_name,
                   buyer.name AS buyer_name, buyer.phone AS buyer_phone,
                   seller.name AS seller_name, seller.phone AS seller_phone
            FROM listing_interests li
            JOIN listings l ON li.listing_id = l.id
            JOIN products p ON l.product_id = p.id
            JOIN users buyer ON li.user_id = buyer.id
            JOIN users seller ON l.user_id = seller.id
            WHERE li.id = %s
        """, (interest_id,))
        interest = cur.fetchone()
        cur.close()
        if not interest:
            raise HTTPException(status_code=404, detail="Interest not found")
        return {"status": "ok", "data": interest}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN GET INTEREST ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Verifications ───────────────────────────────────────────────────────

@router.get("/verifications/pending")
def admin_pending_verifications(_auth=Depends(get_current_admin)):
    try:
        pending = get_pending_verifications()
        return {"status": "ok", "data": pending}
    except Exception as e:
        print(f"ADMIN PENDING VERIFICATIONS ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/verifications/{user_id}/approve")
def admin_approve_verification(user_id: str, _auth=Depends(get_current_admin)):
    try:
        result = approve_verification(user_id)
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])

        from utils.whatsapp import send_whatsapp_reply
        notification = (
            "✅ *Account Verified!*\n\n"
            "Your Moonso Link account has been verified. "
            "Your listings are now visible to all buyers! 🎉"
        )
        if result.get("whatsapp_chat_id"):
            try:
                send_whatsapp_reply(result["whatsapp_chat_id"], notification)
            except Exception as e:
                print(f"VERIFICATION APPROVE WHATSAPP NOTIFY ERROR: {e}")
        if result.get("telegram_id"):
            try:
                import os
                import requests
                tg_token = os.getenv("TELEGRAM_TOKEN")
                if tg_token:
                    requests.post(
                        f"https://api.telegram.org/bot{tg_token}/sendMessage",
                        json={"chat_id": result["telegram_id"], "text": notification, "parse_mode": "Markdown"},
                        timeout=10,
                    )
            except Exception as e:
                print(f"VERIFICATION APPROVE TELEGRAM NOTIFY ERROR: {e}")

        return {"status": "ok", "message": result["message"]}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN APPROVE VERIFICATION ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/verifications/{user_id}/reject")
def admin_reject_verification(user_id: str, _auth=Depends(get_current_admin)):
    try:
        result = reject_verification(user_id)
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])

        from utils.whatsapp import send_whatsapp_reply
        notification = (
            "❌ *Verification Rejected*\n\n"
            "Unfortunately, your account verification could not be approved. "
            "Please submit new documents by sending 'verify my account' again.\n\n"
            "Requirements: clear selfie + ID card photo (JPEG/PNG/PDF, max 2MB each)."
        )
        if result.get("whatsapp_chat_id"):
            try:
                send_whatsapp_reply(result["whatsapp_chat_id"], notification)
            except Exception as e:
                print(f"VERIFICATION REJECT WHATSAPP NOTIFY ERROR: {e}")
        if result.get("telegram_id"):
            try:
                import os
                import requests
                tg_token = os.getenv("TELEGRAM_TOKEN")
                if tg_token:
                    requests.post(
                        f"https://api.telegram.org/bot{tg_token}/sendMessage",
                        json={"chat_id": result["telegram_id"], "text": notification, "parse_mode": "Markdown"},
                        timeout=10,
                    )
            except Exception as e:
                print(f"VERIFICATION REJECT TELEGRAM NOTIFY ERROR: {e}")

        return {"status": "ok", "message": result["message"]}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN REJECT VERIFICATION ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Reports ─────────────────────────────────────────────────────────────

@router.get("/reports")
def admin_list_reports(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _auth=Depends(get_current_admin),
):
    try:
        result = get_reports(status=status)
        if isinstance(result, list):
            total = len(result)
            offset = (page - 1) * limit
            page_items = result[offset:offset + limit]
            return {
                "status": "ok",
                "data": {
                    "total": total,
                    "page": page,
                    "limit": limit,
                    "total_pages": max(1, -(-total // limit)),
                    "reports": page_items,
                },
            }
        return {"status": "ok", "data": result}
    except Exception as e:
        print(f"ADMIN LIST REPORTS ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/reports/{report_id}")
def admin_update_report(report_id: int, body: UpdateReportRequest, _auth=Depends(get_current_admin)):
    try:
        result = update_report_status(report_id, body.status)
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
        return {"status": "ok", "data": result["report"]}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN UPDATE REPORT ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Issues ──────────────────────────────────────────────────────────────

@router.get("/issues")
def admin_list_issues(
    status: Optional[str] = None,
    issue_type: Optional[str] = None,
    region: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _auth=Depends(get_current_admin),
):
    try:
        result = get_issues(product_name=None, issue_type=issue_type, region=region, status=status)
        if isinstance(result, list):
            total = len(result)
            offset = (page - 1) * limit
            page_items = result[offset:offset + limit]
            return {
                "status": "ok",
                "data": {
                    "total": total,
                    "page": page,
                    "limit": limit,
                    "total_pages": max(1, -(-total // limit)),
                    "issues": page_items,
                },
            }
        return {"status": "ok", "data": result}
    except Exception as e:
        print(f"ADMIN LIST ISSUES ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/issues/{issue_id}")
def admin_update_issue(issue_id: int, body: UpdateIssueRequest, _auth=Depends(get_current_admin)):
    try:
        result = update_issue_status(issue_id, body.status)
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
        return {"status": "ok", "data": result["issue"]}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN UPDATE ISSUE ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Advice ──────────────────────────────────────────────────────────────


@router.post("/advice")
def admin_create_advice(body: CreateAdviceRequest, _auth=Depends(get_current_admin)):
    try:
        admin_user_id, _ = _auth
        result = _create_advice(
            title=body.title, content=body.content, author_id=admin_user_id,
            issue_id=body.issue_id, product_name=body.product_name,
            issue_type=body.issue_type, is_verified=body.is_verified,
        )
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
        return {"status": "ok", "data": result["advice"]}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN CREATE ADVICE ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/advice")
def admin_list_advice(
    product_name: Optional[str] = Query(None),
    issue_type: Optional[str] = Query(None),
    is_verified: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _auth=Depends(get_current_admin),
):
    try:
        all_items = _get_all_advice(
            product_name=product_name, issue_type=issue_type, is_verified=is_verified,
        )
        total = len(all_items)
        total_pages = max(1, -(-total // limit)) if total else 1
        offset = (page - 1) * limit
        items = all_items[offset:offset + limit]
        return {
            "status": "ok",
            "data": {
                "total": total,
                "page": page,
                "limit": limit,
                "total_pages": total_pages,
                "advice": items,
            },
        }
    except Exception as e:
        print(f"ADMIN LIST ADVICE ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/advice/{advice_id}")
def admin_get_advice(advice_id: int, _auth=Depends(get_current_admin)):
    try:
        item = _get_advice(advice_id)
        if not item:
            raise HTTPException(status_code=404, detail="Advice not found")
        return {"status": "ok", "data": item}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN GET ADVICE ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/advice/{advice_id}")
def admin_update_advice(advice_id: int, body: UpdateAdviceRequest, _auth=Depends(get_current_admin)):
    try:
        updates = {}
        if body.title is not None:
            updates["title"] = body.title
        if body.content is not None:
            updates["content"] = body.content
        if body.issue_id is not None:
            updates["issue_id"] = body.issue_id
        if body.product_name is not None:
            updates["product_name"] = body.product_name
        if body.issue_type is not None:
            updates["issue_type"] = body.issue_type
        if body.is_verified is not None:
            updates["is_verified"] = body.is_verified

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = _update_advice(advice_id, updates)
        if result["status"] == "error":
            raise HTTPException(status_code=404, detail=result["message"])
        return {"status": "ok", "data": result["advice"]}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN UPDATE ADVICE ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/advice/{advice_id}")
def admin_delete_advice(advice_id: int, _auth=Depends(get_current_admin)):
    try:
        result = _delete_advice(advice_id)
        if result["status"] == "error":
            raise HTTPException(status_code=404, detail=result["message"])
        return {"status": "ok", "message": "Advice deleted"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN DELETE ADVICE ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Products ────────────────────────────────────────────────────────────

VALID_PRODUCT_TYPES = ("crop", "animal", "tool", "service")


@router.post("/products")
def admin_create_product(body: CreateProductRequest, _auth=Depends(get_current_admin)):
    try:
        if body.type not in VALID_PRODUCT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid type. Must be one of: {', '.join(VALID_PRODUCT_TYPES)}"
            )
        product_id = _create_product(body.name, body.type, body.default_measurement)
        if not product_id:
            raise HTTPException(status_code=400, detail="Failed to create product (may already exist)")
        product = _get_product_info(body.name)
        return {"status": "ok", "data": product}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN CREATE PRODUCT ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/products")
def admin_list_products(
    type: Optional[str] = Query(None, alias="type"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _auth=Depends(get_current_admin),
):
    try:
        if type and type not in VALID_PRODUCT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid type filter. Must be one of: {', '.join(VALID_PRODUCT_TYPES)}"
            )
        all_items = _get_all_products(product_type=type)
        total = len(all_items)
        total_pages = max(1, -(-total // limit)) if total else 1
        offset = (page - 1) * limit
        items = all_items[offset:offset + limit]
        return {
            "status": "ok",
            "data": {
                "total": total,
                "page": page,
                "limit": limit,
                "total_pages": total_pages,
                "products": items,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN LIST PRODUCTS ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/products/{product_id}")
def admin_get_product(product_id: int, _auth=Depends(get_current_admin)):
    try:
        cur = _db_conn.cursor()
        cur.execute("SELECT * FROM products WHERE id = %s", (product_id,))
        product = cur.fetchone()
        cur.close()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        return {"status": "ok", "data": product}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN GET PRODUCT ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/products/{product_id}")
def admin_update_product(product_id: int, body: UpdateProductRequest, _auth=Depends(get_current_admin)):
    try:
        updates = {}
        if body.name is not None:
            updates["name"] = body.name.strip().lower()
        if body.type is not None:
            if body.type not in VALID_PRODUCT_TYPES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid type. Must be one of: {', '.join(VALID_PRODUCT_TYPES)}"
                )
            updates["type"] = body.type
        if body.default_measurement is not None:
            updates["default_measurement"] = body.default_measurement

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = _update_product(product_id, updates)
        if result["status"] == "error":
            raise HTTPException(status_code=404, detail=result["message"])
        return {"status": "ok", "data": result["product"]}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN UPDATE PRODUCT ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/products/{product_id}")
def admin_delete_product(product_id: int, _auth=Depends(get_current_admin)):
    try:
        result = _delete_product(product_id)
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
        return {"status": "ok", "message": "Product deleted"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN DELETE PRODUCT ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Product Prices ──────────────────────────────────────────────────────

VALID_REGIONS = (
    "Adamaoua", "Centre", "Est", "Extreme-Nord", "Littoral",
    "Nord", "Nord-Ouest", "Ouest", "Sud", "Sud-Ouest", "General",
)


@router.post("/product-prices")
def admin_create_product_price(body: CreateProductPriceRequest, _auth=Depends(get_current_admin)):
    try:
        if body.region not in VALID_REGIONS:
            raise HTTPException(status_code=400, detail=f"Invalid region. Must be one of: {', '.join(VALID_REGIONS)}")
        if not (body.min_price <= body.avg_price <= body.max_price):
            raise HTTPException(status_code=400, detail="Must satisfy: min_price <= avg_price <= max_price")
        result = _create_product_price(body.product_id, body.region, body.min_price, body.max_price, body.avg_price)
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
        return {"status": "ok", "data": result["product_price"]}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN CREATE PRODUCT PRICE ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/product-prices")
def admin_list_product_prices(
    product_id: Optional[int] = Query(None),
    region: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _auth=Depends(get_current_admin),
):
    try:
        if region and region not in VALID_REGIONS:
            raise HTTPException(status_code=400, detail=f"Invalid region. Must be one of: {', '.join(VALID_REGIONS)}")
        all_items = _get_product_prices(product_id=product_id, region=region)
        total = len(all_items)
        total_pages = max(1, -(-total // limit)) if total else 1
        offset = (page - 1) * limit
        items = all_items[offset:offset + limit]
        return {
            "status": "ok",
            "data": {
                "total": total,
                "page": page,
                "limit": limit,
                "total_pages": total_pages,
                "product_prices": items,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN LIST PRODUCT PRICES ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/product-prices/{price_id}")
def admin_get_product_price(price_id: int, _auth=Depends(get_current_admin)):
    try:
        cur = _db_conn.cursor()
        cur.execute("""
            SELECT pp.*, p.name AS product_name, p.type AS product_type
            FROM product_prices pp
            JOIN products p ON pp.product_id = p.id
            WHERE pp.id = %s
        """, (price_id,))
        price = cur.fetchone()
        cur.close()
        if not price:
            raise HTTPException(status_code=404, detail="Product price not found")
        return {"status": "ok", "data": price}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN GET PRODUCT PRICE ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/product-prices/{price_id}")
def admin_update_product_price(price_id: int, body: UpdateProductPriceRequest, _auth=Depends(get_current_admin)):
    try:
        updates = {}
        if body.region is not None:
            if body.region not in VALID_REGIONS:
                raise HTTPException(status_code=400, detail=f"Invalid region. Must be one of: {', '.join(VALID_REGIONS)}")
            updates["region"] = body.region
        if body.min_price is not None:
            updates["min_price"] = body.min_price
        if body.max_price is not None:
            updates["max_price"] = body.max_price
        if body.avg_price is not None:
            updates["avg_price"] = body.avg_price

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        result = _update_product_price(price_id, updates)
        if result["status"] == "error":
            raise HTTPException(status_code=404, detail=result["message"])
        return {"status": "ok", "data": result["product_price"]}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN UPDATE PRODUCT PRICE ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/product-prices/{price_id}")
def admin_delete_product_price(price_id: int, _auth=Depends(get_current_admin)):
    try:
        result = _delete_product_price(price_id)
        if result["status"] == "error":
            raise HTTPException(status_code=404, detail=result["message"])
        return {"status": "ok", "message": "Product price deleted"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN DELETE PRODUCT PRICE ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Locations ───────────────────────────────────────────────────────────

VALID_LOCATION_REGIONS = (
    "Adamaoua", "Centre", "Est", "Extreme-Nord", "Littoral",
    "Nord", "Nord-Ouest", "Ouest", "Sud", "Sud-Ouest", "General",
)


@router.post("/locations")
def admin_create_location(body: CreateLocationRequest, _auth=Depends(get_current_admin)):
    try:
        if body.region not in VALID_LOCATION_REGIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid region. Must be one of: {', '.join(VALID_LOCATION_REGIONS)}"
            )
        result = _create_location(body.town.strip(), body.region, body.department)
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
        return {"status": "ok", "data": result["location"]}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN CREATE LOCATION ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/locations")
def admin_list_locations(
    town: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _auth=Depends(get_current_admin),
):
    try:
        if region and region not in VALID_LOCATION_REGIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid region. Must be one of: {', '.join(VALID_LOCATION_REGIONS)}"
            )
        all_items = _get_all_locations(town=town, region=region)
        total = len(all_items)
        total_pages = max(1, -(-total // limit)) if total else 1
        offset = (page - 1) * limit
        items = all_items[offset:offset + limit]
        return {
            "status": "ok",
            "data": {
                "total": total,
                "page": page,
                "limit": limit,
                "total_pages": total_pages,
                "locations": items,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN LIST LOCATIONS ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/locations/{location_id}")
def admin_get_location(location_id: int, _auth=Depends(get_current_admin)):
    try:
        location = _get_location(location_id)
        if not location:
            raise HTTPException(status_code=404, detail="Location not found")
        return {"status": "ok", "data": location}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN GET LOCATION ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/locations/{location_id}")
def admin_update_location(location_id: int, body: UpdateLocationRequest, _auth=Depends(get_current_admin)):
    try:
        updates = {}
        if body.town is not None:
            updates["town"] = body.town.strip()
        if body.region is not None:
            if body.region not in VALID_LOCATION_REGIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid region. Must be one of: {', '.join(VALID_LOCATION_REGIONS)}"
                )
            updates["region"] = body.region
        if body.department is not None:
            updates["department"] = body.department

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = _update_location(location_id, updates)
        if result["status"] == "error":
            raise HTTPException(status_code=404, detail=result["message"])
        return {"status": "ok", "data": result["location"]}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN UPDATE LOCATION ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/locations/{location_id}")
def admin_delete_location(location_id: int, _auth=Depends(get_current_admin)):
    try:
        result = _delete_location(location_id)
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])
        return {"status": "ok", "message": "Location deleted"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN DELETE LOCATION ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Logs (Read-only) ────────────────────────────────────────────────────


@router.get("/logs/messages")
def admin_list_message_logs(
    platform: Optional[str] = Query(None),
    intent: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _auth=Depends(get_current_admin),
):
    try:
        result = _get_message_logs(platform=platform, intent=intent, user_id=user_id, page=page, limit=limit)
        return {"status": "ok", "data": result}
    except Exception as e:
        print(f"ADMIN LIST MESSAGE LOGS ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/logs/messages/{log_id}")
def admin_get_message_log(log_id: int, _auth=Depends(get_current_admin)):
    try:
        log = _get_message_log(log_id)
        if not log:
            raise HTTPException(status_code=404, detail="Message log not found")
        return {"status": "ok", "data": log}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN GET MESSAGE LOG ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/logs/assistant")
def admin_list_assistant_logs(
    intent: Optional[str] = Query(None),
    method: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _auth=Depends(get_current_admin),
):
    try:
        result = _get_assistant_logs(intent=intent, method=method, page=page, limit=limit)
        return {"status": "ok", "data": result}
    except Exception as e:
        print(f"ADMIN LIST ASSISTANT LOGS ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/logs/assistant/{log_id}")
def admin_get_assistant_log(log_id: int, _auth=Depends(get_current_admin)):
    try:
        log = _get_assistant_log(log_id)
        if not log:
            raise HTTPException(status_code=404, detail="Assistant log not found")
        return {"status": "ok", "data": log}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN GET ASSISTANT LOG ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/logs/states")
def admin_list_conversation_states(
    state: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _auth=Depends(get_current_admin),
):
    try:
        result = _get_all_conversation_states(state=state, page=page, limit=limit)
        return {"status": "ok", "data": result}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN LIST CONVERSATION STATES ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/logs/states/{state_id}")
def admin_get_conversation_state(state_id: int, _auth=Depends(get_current_admin)):
    try:
        state = _get_conversation_state_detail(state_id)
        if not state:
            raise HTTPException(status_code=404, detail="Conversation state not found")
        return {"status": "ok", "data": state}
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN GET CONVERSATION STATE ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Alerts ──────────────────────────────────────────────────────────────

VALID_ALERT_TYPES = ("disease_outbreak", "product_shortage", "general")


@router.get("/alerts")
def admin_list_alerts(
    alert_type: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _auth=Depends(get_current_admin),
):
    try:
        if alert_type and alert_type not in VALID_ALERT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid alert_type. Must be one of: {', '.join(VALID_ALERT_TYPES)}"
            )
        all_items = _get_alerts(alert_type=alert_type, region=region)
        total = len(all_items)
        total_pages = max(1, -(-total // limit)) if total else 1
        offset = (page - 1) * limit
        items = all_items[offset:offset + limit]
        return {
            "status": "ok",
            "data": {
                "total": total,
                "page": page,
                "limit": limit,
                "total_pages": total_pages,
                "alerts": items,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN LIST ALERTS ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/alerts")
def admin_create_alert(body: CreateAlertRequest, _auth=Depends(get_current_admin)):
    try:
        admin_user_id, _ = _auth

        if body.alert_type not in VALID_ALERT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid alert_type. Must be one of: {', '.join(VALID_ALERT_TYPES)}"
            )

        result = _create_alert(
            title=body.title,
            alert_type=body.alert_type,
            created_by=admin_user_id,
            description=body.description,
            region=body.region,
            product_name=body.product_name,
            source_report_id=body.source_report_id,
            expires_at=body.expires_at,
        )
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result["message"])

        contacts = get_all_user_contacts(region=body.region)

        notification = f"🚨 *{body.title}*\n\n"
        if body.description:
            notification += f"{body.description}\n\n"
        notification += (
            f"Type: {body.alert_type.replace('_', ' ').title()}\n"
            f"Region: {body.region.replace('_', ' ').title() if body.region else 'All regions'}"
        )

        from utils.whatsapp import send_whatsapp_reply
        import os
        import requests

        whatsapp_sent = 0
        telegram_sent = 0

        for user in contacts:
            if user.get("whatsapp_chat_id"):
                try:
                    send_whatsapp_reply(user["whatsapp_chat_id"], notification)
                    whatsapp_sent += 1
                except Exception as e:
                    print(f"ALERT WHATSAPP SEND ERROR (user {user['id']}): {e}")
            if user.get("telegram_id"):
                try:
                    tg_token = os.getenv("TELEGRAM_TOKEN")
                    if tg_token:
                        requests.post(
                            f"https://api.telegram.org/bot{tg_token}/sendMessage",
                            json={"chat_id": user["telegram_id"], "text": notification, "parse_mode": "Markdown"},
                            timeout=10,
                        )
                        telegram_sent += 1
                except Exception as e:
                    print(f"ALERT TELEGRAM SEND ERROR (user {user['id']}): {e}")

        return {
            "status": "ok",
            "data": {
                "alert": result["alert"],
                "notified_count": len(contacts),
                "whatsapp_sent": whatsapp_sent,
                "telegram_sent": telegram_sent,
            },
            "message": f"Alert created and sent to {len(contacts)} users"
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"ADMIN CREATE ALERT ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")
