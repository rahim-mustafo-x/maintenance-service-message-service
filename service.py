from pymongo import MongoClient
from starlette.websockets import WebSocket
from repository import ConversationRepository, RoomRepository
from model import Conversation, Room, Page, ChatType, Session
from websocket_manager import MessageMembersManager
from uuid import uuid4
from jwt import decode, ExpiredSignatureError, InvalidSignatureError, DecodeError, ImmatureSignatureError
from config import JWT_SECRET_KEY
from config import MONGODB_URL, PING, PONG
from connection import Presence
from typing import Optional
from asyncio import sleep

#uuid4 is natural random thing while others demand time and mac address this one is random
_client = MongoClient(MONGODB_URL)
_db_name = "message_app"

_room_repo = RoomRepository(_client, _db_name)
_conv_repo = ConversationRepository(_client, _db_name)
_presence = Presence()
_message_members_manager = MessageMembersManager()

async def start_conversation(auth:str, websocket:WebSocket) -> bool:
    user_id = _user_id(auth)
    if user_id !=-1:
        session = Session(session_id=str(uuid4()), user_id = user_id, time_to_live=30, chat_id=None, chat_type=None)
        await _presence.set_presence(session)
        await _message_members_manager.connect(session.session_id, websocket)
        return True
    else:
        return False

def conversations(auth:str, page:int, size: int) -> Optional[Page[Conversation]]:
    user_id = _user_id(auth)
    if user_id !=-1:
        return _conv_repo.get_conversations_by_user(user_id, page, size)
    else:
        return None

def _user_id(auth:str)->int:
    try:
        token = auth.split(' ')[1]
        user = decode(token, JWT_SECRET_KEY, 'HS256')
        return user['userId']
    except ExpiredSignatureError, InvalidSignatureError, DecodeError, ImmatureSignatureError:
        return -1

async def receive_text(text:str):
    if text==PONG:
        # _presence.set_presence()
        pass

async def heartbeat(auth:str):
    user_id = _user_id(auth)
    if user_id ==-1:
        return
    session = _presence.get_presence(user_id)
    if session is Session:
        await sleep(session.time_to_live)
        await _message_members_manager.send_message(session.sesion_id, PING)