from pymongo import MongoClient
from repository import ConversationRepository, RoomRepository
from model import Conversation, Room, Page
from uuid import uuid4
from jwt import decode, ExpiredSignatureError, InvalidSignatureError, DecodeError, ImmatureSignatureError
from config import JWT_SECRET_KEY
from config import MONGODB_URL

#uuid4 is natural random thing while others demand time and mac address this one is random

_client = MongoClient(MONGODB_URL)
_db_name = "message_app"

_room_repo = RoomRepository(_client, _db_name)
_conv_repo = ConversationRepository(_client, _db_name)

def start_conversation():
    pass

def conversations(auth:str, page:int, size: int) -> Page[Conversation]:
    return _conv_repo.get_conversations_by_user(_user_id(auth), page, size)

def _user_id(auth:str)->int:
    try:
        token = auth.split(' ')[1]
        user = decode(token, JWT_SECRET_KEY, 'HS256')
        return user['userId']
    except ExpiredSignatureError, InvalidSignatureError, DecodeError, ImmatureSignatureError:
        return -1