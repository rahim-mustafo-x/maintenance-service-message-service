from fastapi import (FastAPI, WebSocket, WebSocketDisconnect, Request)
from fastapi.responses import FileResponse

from model import Page, Conversation
from websocket_manager import MessageMembersManager
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from config import APP_NAME
import service

_middleware = [
    Middleware(
        CORSMiddleware,  # type: ignore
        allow_origins=["*"],# type: ignore
        allow_credentials=True,# type: ignore
        allow_methods=["*"],# type: ignore
        allow_headers=["*"],# type: ignore
    )
]
app = FastAPI(middleware=_middleware,
servers=[
    {
        'url':f'/{APP_NAME}',
        'description':'via api gateway'
    },
    {
        'url':'/',
        'description':'local server'
    }
])


_message_members_manager = MessageMembersManager()

@app.websocket('/ws/chat/{user_id}')
async def websocket_endpoint(websocket: WebSocket, user_id:int):
    await _message_members_manager.connect(user_id, websocket)
    try:
        while True:
            text = await websocket.receive_text()
            await _message_members_manager.send_message(user_id, text, websocket)
    except WebSocketDisconnect:
        _message_members_manager.disconnect(user_id, websocket)
@app.get('/favicon.ico')
async def favicon():
    return FileResponse('favicon.ico')

@app.get('/')
async def index():
    return FileResponse('index.html')

@app.get('/conversations', response_model=Page[Conversation])
async def conversations(request: Request, page: int = 1, size: int = 10):
    auth = str(request.headers.get('Authorization'))
    return service.conversations(auth, page, size)