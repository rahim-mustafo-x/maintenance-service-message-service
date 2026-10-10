from datetime import datetime, timezone
from enum import Enum
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field


class ChatType(str, Enum):
    CONVERSATION = "conversation"
    ROOM = "room"


class User(BaseModel):
    user_id: int
    name: str
    email: str
    profile_image: Optional[str] = None

class Session(BaseModel):
    session_id: str
    user_id: int

    chat_id: Optional[str] = None
    chat_type: Optional[ChatType] = None

    time_to_live: int = 30


class Conversation(BaseModel):
    conversation_id: str
    name: str
    profile_image: Optional[str] = None
    people: List[int] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Room(BaseModel):
    room_id: str
    conversation_id: str
    text: Optional[str] = None
    who_sent: int
    # Canonical persisted image representation: URLs in the legacy-compatible images array.
    images: List[str] = Field(default_factory=list)
    # Image Service UUIDs allow cleanup of the uploaded binary assets on deletion.
    image_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Defaults keep historical MongoDB documents readable without migration.
    is_edited: bool = False
    is_deleted: bool = False
    updated_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None


class EditMessageRequest(BaseModel):
    # Both fields are optional so PATCH can update text, images, or both.
    # image_url is a convenience alias for a single-image client; images remains canonical.
    text: Optional[str] = None
    images: Optional[List[str]] = None
    image_url: Optional[str] = None
    image_ids: Optional[List[str]] = None


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: List[T]
    total_pages: int
    page: int
    size: int