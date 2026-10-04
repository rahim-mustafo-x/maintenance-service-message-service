from fastapi import (WebSocket, WebSocketDisconnect)
from typing import Optional

class MessageMembersManager:
    def __init__(self):
        #             session_id   chat_id  websocket
        self.members:dict[str, Optional[WebSocket]] = {}
    async def connect(self, session_id:str, ws:WebSocket):
        await ws.accept()
        if session_id not in self.members:
            #creates a new group
            self.members[session_id] = ws
    def disconnect(self, session_id:str,ws:WebSocket):
        if session_id in self.members:
            self.members[session_id].remove(ws)
            if not self.members[session_id]:
                del self.members[session_id]

    #sends message to user itself from server to user
    async def send_message(self, session_id:str, message:str):
        if session_id not in self.members:
            return
        ws = self.members[session_id]
        if ws is None:
            return
        try:
            await ws.send_text(message)
        except WebSocketDisconnect:
            self.disconnect(session_id,ws)