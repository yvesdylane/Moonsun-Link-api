from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID


@dataclass
class User:
    """User model matching the database schema"""
    id: UUID
    user_id: Optional[str]
    name: str
    phone: Optional[str]
    email: Optional[str]
    role: str  # 'farmer', 'buyer', 'admin'
    region: str
    telegram_id: Optional[str]
    telegram_number: Optional[str]
    whatsapp_number: Optional[str]
    lang: str  # 'en', 'fr'
    pic_folder: Optional[str]
    created_at: datetime
    updated_at: datetime
    verified: str  # 'true', 'false', 'pending'
    linking_code: Optional[str]
    code_expire_at: Optional[datetime]

    @classmethod
    def from_db_row(cls, row: tuple) -> 'User':
        """
        Create User from database row tuple.
        Expected order from SELECT * FROM users:
        (id, user_id, name, phone, email, role, region, telegram_id,
         telegram_number, whatsapp_number, lang, pic_folder, created_at,
         updated_at, verified, linking_code, code_expire_at)
        """
        return cls(
            id=row[0],
            user_id=row[1],
            name=row[2],
            phone=row[3],
            email=row[4],
            role=row[5],
            region=row[6],
            telegram_id=row[7],
            telegram_number=row[8],
            whatsapp_number=row[9],
            lang=row[10],
            pic_folder=row[11],
            created_at=row[12],
            updated_at=row[13],
            verified=row[14],
            linking_code=row[15],
            code_expire_at=row[16]
        )

    def is_farmer(self) -> bool:
        return self.role == 'farmer'

    def is_buyer(self) -> bool:
        return self.role == 'buyer'

    def is_admin(self) -> bool:
        return self.role == 'admin'

    def is_verified(self) -> bool:
        return self.verified == 'true'

    def is_pending_verification(self) -> bool:
        return self.verified == 'pending'

    def get_lang_display(self) -> str:
        """Get language display string, handling None"""
        return (self.lang or 'en').upper()

    def get_verification_status_display(self) -> str:
        """Get formatted verification status"""
        if self.verified == 'true':
            return "✅ Verified"
        elif self.verified == 'pending':
            return "⏳ Pending verification"
        else:
            return "❌ Not verified"
