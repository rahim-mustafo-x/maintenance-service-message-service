from pydantic import BaseModel
from typing import List, TypeVar, Generic, Optional

class Conversation(BaseModel):
    conversation_id:str
    name:str
    profile_image:str#image links

class Room(BaseModel):
    room_id:str
    conversation_id:str
    text:Optional[str]
    who_sent:int
    images:Optional[list[str]]#image links use grid depending on the count of image

T = TypeVar('T')

class Page(BaseModel, Generic[T]):
    items: List[T]
    total_pages:int
    page:int
    size:int

class Session(BaseModel):
    session_id:str#uuid4 as well
    user_id:int
    chat_id:Optional[str]
    chat_type:Optional[ChatType]#conversation or room
    time_to_live:int

from enum import Enum
class ChatType(Enum):
    CONVERSATION = 0
    ROOM = 1