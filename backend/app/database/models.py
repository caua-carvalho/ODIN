from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), default="New Conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant | system | tool
    content: Mapped[str] = mapped_column(Text, default="")
    tool_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tool_call_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PermissionRequest(Base):
    __tablename__ = "permission_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(36), index=True)
    tool: Mapped[str] = mapped_column(String(100))
    operation: Mapped[str] = mapped_column(String(50))
    arguments_json: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    target: Mapped[str] = mapped_column(String(500))
    reason: Mapped[str] = mapped_column(Text, default="")
    risk_level: Mapped[str] = mapped_column(String(20), default="medium")  # low | medium | high | critical
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | approved | denied | expired
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
