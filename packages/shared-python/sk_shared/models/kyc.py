from datetime import datetime
from typing import Optional, TYPE_CHECKING
import enum

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, Integer, LargeBinary, String, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from .auth import AdminUser, User


class KycStatus(str, enum.Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class CustomerProfile(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "customer_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # KMS-encrypted at rest (see KycService.upsert_profile) — not unique-checkable
    # since encryption isn't deterministic; a separate CNIC-hash column would be
    # needed to enforce "one profile per real CNIC" without decrypting every row.
    cnic: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    dob: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    user: Mapped["User"] = relationship("User")


class UserKycVerification(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "user_kyc_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # values_callable: the Postgres `kycstatus` enum type stores lowercase values
    # (KycStatus.PENDING.value == "pending"); SQLAlchemy's default Enum binding
    # sends the member NAME ("PENDING") instead, which the DB type rejects.
    status: Mapped[KycStatus] = mapped_column(
        Enum(KycStatus, name="kycstatus", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        default=KycStatus.PENDING,
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cnic_front_image_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cnic_back_image_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    liveness_video_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    nadra_verification_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    shufti_verification_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    rejection_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    nadra_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User")
    
    __table_args__ = (
        Index("ix_user_kyc_verifications_user_id", "user_id"),
        Index("ix_user_kyc_verifications_status", "status"),
    )


class KycVerificationQueue(Base, TimestampMixin):
    __tablename__ = "kyc_verification_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kyc_verification_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user_kyc_verifications.id", ondelete="CASCADE"), unique=True, nullable=False)
    assigned_admin_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    kyc_verification: Mapped["UserKycVerification"] = relationship("UserKycVerification")
    assigned_admin: Mapped["AdminUser"] = relationship("AdminUser")

    __table_args__ = (
        Index("ix_kyc_verification_queue_assigned", "assigned_admin_id"),
    )
