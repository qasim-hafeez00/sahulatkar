import uuid as uuid_pkg
from datetime import datetime
from typing import Optional

from sqlalchemy import UUID, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.ext.hybrid import hybrid_property

class Base(DeclarativeBase):
    pass

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

class UUIDMixin:
    uuid: Mapped[uuid_pkg.UUID] = mapped_column(UUID(as_uuid=True), default=uuid_pkg.uuid4, unique=True, nullable=False)

class SoftDeleteMixin:
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    @hybrid_property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
