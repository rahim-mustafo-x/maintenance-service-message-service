import asyncio

from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    Request,
    HTTPException,
    Query,
    APIRouter,
)
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBearer
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from model import Page, Conversation, Room
from config import APP_NAME
import service

_middleware = [
    Middleware(
        CORSMiddleware,#type:ignore
        allow_origins=["*"],#type:ignore
        allow_credentials=True,#type:ignore
        allow_methods=["*"],#type:ignore
        allow_headers=["*"],#type:ignore
    )
]
bearer_scheme = HTTPBearer()

app = FastAPI(
    root_path=f"/{APP_NAME}",
    middleware=_middleware,
    servers=[
        {"url": f"/{APP_NAME}", "description": "via api gateway"},
        {"url": "/", "description": "local server"},
    ],
)

v1_router = APIRouter(prefix="/v1")

@v1_router.websocket("/ws/chat")
async def websocket_endpoint_v1(
    websocket: WebSocket,
    chat_id: str | None = Query(default=None),
):
    auth = websocket.headers.get("Authorization")
    if auth is None:
        auth = websocket.query_params.get("token")
    if auth:
        if auth.startswith("Bearer "): auth = auth[7:]
        elif auth.startswith("bearer "): auth = auth[7:]
    if auth is None:
        await websocket.close(code=1008)
        return
    session = await service.start_conversation(auth=auth, websocket=websocket, chat_id=chat_id)
    if session is None:
        await websocket.close(code=1008)
        return
    heartbeat_task = asyncio.create_task(service.heartbeat(session, websocket))
    try:
        while True:
            message = await websocket.receive()
            if "text" in message:
                await service.receive_text(session, message["text"], websocket)
            elif "bytes" in message:
                await service.receive_bytes(session, message["bytes"])
    except WebSocketDisconnect:
        pass
    finally:
        heartbeat_task.cancel()
        await service.disconnect(session)

@v1_router.get("/conversations", response_model=Page[Conversation])
async def conversations_v1(request: Request, page: int = 1, size: int = 10):
    auth = request.headers.get("Authorization")
    if auth is None: raise HTTPException(status_code=401, detail="Authorization required")
    data = await service.conversations(auth, page, size)
    if data is None: raise HTTPException(status_code=401, detail="Unauthorized")
    return data

@v1_router.get("/conversations/{conversation_id}/messages", response_model=Page[Room])
async def messages_v1(request: Request, conversation_id: str, page: int = 1, size: int = 10):
    auth = request.headers.get("Authorization")
    if auth is None: raise HTTPException(status_code=401, detail="Authorization required")
    return await service.messages(auth=auth, conversation_id=conversation_id, page=page, size=size)

@v1_router.get("/users/search")
async def search_users_v1(request: Request, q: str = Query(...)):
    auth = request.headers.get("Authorization")
    if auth is None: raise HTTPException(status_code=401, detail="Authorization required")
    return await service.search_users(auth, q)

@v1_router.post("/conversations")
async def create_conversation_v1(request: Request, userId: int = Query(...)):
    auth = request.headers.get("Authorization")
    if auth is None: raise HTTPException(status_code=401, detail="Authorization required")
    conv = await service.create_conversation(auth, userId)
    if conv is None: raise HTTPException(status_code=400, detail="Could not create conversation")
    return conv

# Crucial: include the router before the final endpoints
app.include_router(v1_router)

@app.get("/", response_class=HTMLResponse)
async def get_home():
    with open("index.html", "r") as f:
        return f.read()
