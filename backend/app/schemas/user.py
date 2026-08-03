import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    current_celpip_score: int | None = Field(default=None, ge=1, le=12)
    target_celpip_score: int | None = Field(default=None, ge=1, le=12)
    target_exam_date: date | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("first_name")
    @classmethod
    def strip_first_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("first_name cannot be blank")
        return value


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    first_name: str
    current_celpip_score: int | None
    target_celpip_score: int | None
    target_exam_date: date | None
    role: UserRole
    is_active: bool
    created_at: datetime
