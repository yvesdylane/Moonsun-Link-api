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
from db.controller.alertController import create_alert as _create_alert, get_all_user_contacts

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


# ── Alerts ──────────────────────────────────────────────────────────────

VALID_ALERT_TYPES = ("disease_outbreak", "product_shortage", "general")


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
