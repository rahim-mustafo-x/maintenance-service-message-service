from enum import Enum
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel


class ChatType(str, Enum):
    CONVERSATION = "conversation"
    ROOM = "room"


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
    people: List[int] = []


class Room(BaseModel):
    room_id: str
    conversation_id: str
    text: Optional[str] = None
    who_sent: int
    images: List[str] = []


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: List[T]
    total_pages: int
    page: int
    size: int