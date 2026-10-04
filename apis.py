import asyncio

from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    Request,
    HTTPException,
    Query,
    Depends,
)
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
    dependencies=[Depends(bearer_scheme)],
    middleware=_middleware,
    servers=[
        {
            "url": f"/{APP_NAME}",
            "description": "via api gateway",
        },
        {
            "url": "/",
            "description": "local server",
        },
    ],
)


@app.websocket("/ws/chat")
async def websocket_endpoint(
    websocket: WebSocket,
    chat_id: str | None = Query(default=None),
):
    auth = websocket.headers.get("Authorization")

    if auth is None:
        await websocket.close(code=1008)
        return

    if chat_id is None:
        await websocket.close(code=1008)
        return

    session = await service.start_conversation(
        auth=auth,
        websocket=websocket,
        chat_id=chat_id,
    )

    if session is None:
        await websocket.close(code=1008)
        return

    heartbeat_task = asyncio.create_task(
        service.heartbeat(session)
    )

    try:
        while True:
            text = await websocket.receive_text()

            await service.receive_text(
                session,
                text,
            )

    except WebSocketDisconnect:
        pass

    finally:
        heartbeat_task.cancel()

        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

        await service.disconnect(session)


@app.get(
    "/conversations",
    response_model=Page[Conversation],
)
async def conversations(
    request: Request,
    page: int = 1,
    size: int = 10,
):
    auth = request.headers.get("Authorization")

    if auth is None:
        raise HTTPException(
            status_code=401,
            detail="Authorization required",
        )

    data = await service.conversations(
        auth,
        page,
        size,
    )

    if data is None:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
        )

    return data


@app.get(
    "/conversations/{conversation_id}/messages",
    response_model=Page[Room],
)
async def messages(
    request: Request,
    conversation_id: str,
    page: int = 1,
    size: int = 10,
):
    auth = request.headers.get("Authorization")

    if auth is None:
        raise HTTPException(
            status_code=401,
            detail="Authorization required",
        )

    return await service.messages(
        auth=auth,
        conversation_id=conversation_id,
        page=page,
        size=size,
    )