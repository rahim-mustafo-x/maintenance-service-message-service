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
    # Resolved once from USER-SERVICE at connect time and retained in Redis presence.
    display_name: str = ""
    profile_image: Optional[str] = None

    chat_id: Optional[str] = None
    chat_type: Optional[ChatType] = None

    time_to_live: int = 30


class Conversation(BaseModel):
    conversation_id: str
    # Personalized for the authenticated viewer in API/WebSocket responses; never overwrite
    # the shared MongoDB name field with a viewer-specific peer name.
    name: str
    profile_image: Optional[str] = None
    peer_user_id: Optional[int] = None
    peer_name: Optional[str] = None
    peer_phone_number: Optional[str] = None
    people: List[int] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Room(BaseModel):
    room_id: str
    conversation_id: str
    text: Optional[str] = None
    who_sent: int
    # Snapshot of the sender's USER-SERVICE display name at send time.
    sender_name: Optional[str] = None
    # Canonical persisted image representation: URLs in the legacy-compatible images array.
    images: List[str] = Field(default_factory=list)
    # Image Service IDs are internal ownership/cleanup references; image URLs remain client-renderable.
    image_ids: List[Optional[str]] = Field(default_factory=list)
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
    image_ids: Optional[List[Optional[str]]] = None


class ImageCleanupRequest(BaseModel):
    image_ids: List[str] = Field(min_length=1, max_length=10)


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: List[T]
    total_pages: int
    page: int
    size: int