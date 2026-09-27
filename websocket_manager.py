from fastapi import (WebSocket, WebSocketDisconnect)

"""
1.Each user connects to a separate web socket
2.with pub/sub user's status is checked so that if user is offline then they are freed from the memory
3.from database user's conversation is extracted in rest api
4.force connected to one web socket
5.then showed real time updated inside the inbox

https://www.youtube.com/watch?v=xOtrCmPjal8

here is link for pub&sub in redis
"""
class MessageMembersManager:
    def __init__(self):
        self.members:dict[int, list[WebSocket]] = {}
    async def connect(self, user_id:int, ws:WebSocket):
        await ws.accept()
        if user_id not in self.members:
            #creates a new group
            self.members[user_id] = []
        self.members[user_id].append(ws)
    def disconnect(self, user_id:int,ws:WebSocket):
        if user_id in self.members:
            self.members[user_id].remove(ws)
            if not self.members[user_id]:
                del self.members[user_id]
    async def send_message(self, user_id:int, message:str, ws:WebSocket):
        if user_id not in self.members:
            return

        for connection in self.members[user_id]:
            if connection != ws:
                try:
                    await connection.send_text(message)
                except WebSocketDisconnect:
                    self.disconnect(user_id, connection)
