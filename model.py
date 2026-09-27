from pydantic import BaseModel
from typing import List, TypeVar, Generic

class Conversation(BaseModel):
    conversation_id:str
    people:list[int]

class Room(BaseModel):
    room_id:str
    conversation_id:str
    text:str
    who_sent:int
    images:list[str]#image links use grid depending on the count of image

T = TypeVar('T')

class Page(BaseModel, Generic[T]):
    items: List[T]
    total_pages:int
    page:int
    size:int