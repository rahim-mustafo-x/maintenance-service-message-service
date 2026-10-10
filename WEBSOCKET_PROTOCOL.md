# 💬 Message Service: WebSocket Protocol Guide

This document describes the communication flow between the Kotlin client and the Python Message Service. To ensure high performance and scalability across multiple service instances, the system uses a **Unified WebSocket Architecture**.

## 🏗️ Architecture Overview

Instead of using multiple REST API calls for history and lists, the client establishes **one single authenticated WebSocket connection**. This connection handles:
1.  **Identity**: JWT-based authentication.
2.  **Presence**: Single-connection enforcement via Redis.
3.  **Health**: Binary PING/PONG heartbeats.
4.  **Operations**: All chat-related actions (Listing, Opening, Messaging, History).
5.  **Real-time**: Cross-instance message delivery via Redis Pub/Sub.

---

## 🚀 The Conversation Flow

### 1. Connection & Authentication
The client connects to the WebSocket endpoint.

- **Endpoint**: `ws://<service-url>/v1/ws/chat?chat_id=<initial_id>`
- **Header**: `Authorization: Bearer <JWT_TOKEN>`
- **Server Action**: Validates JWT, claims session ownership in Redis, and starts the heartbeat loop.

### 2. Finding People (Conversation List)
The client requests a list of existing conversations the user is part of.

**Request:**
```json
{
  "type": "LIST_CONVERSATIONS",
  "request_id": "req_001",
  "payload": { "page": 1, "size": 20 }
}
```

**Response:**
```json
{
  "type": "CONVERSATIONS_LIST",
  "request_id": "req_001",
  "payload": {
    "items": [
      { "conversation_id": "conv_abc", "name": "John Doe", "profile_image": "http://..." },
      { "conversation_id": "conv_xyz", "name": "Jane Smith", "profile_image": null }
    ],
    "total_pages": 1,
    "page": 1,
    "size": 20
  }
}
```
- **REST Alternative (Legacy)**: `GET /v1/conversations`

### 3. Opening a Chat & Loading History
When a user selects a person, the client "opens" that conversation to set the context and loads the message history.

**Step A: Open Conversation**
```json
{
  "type": "OPEN_CONVERSATION",
  "request_id": "req_002",
  "payload": { "chat_id": "conv_abc" }
}
```
*Response: `CONVERSATION_OPENED` event.*

**Step B: Load History**
```json
{
  "type": "GET_HISTORY",
  "request_id": "req_003",
  "payload": { "page": 1, "size": 50 }
}
```
**Response:**
```json
{
  "type": "MESSAGES_PAGE",
  "request_id": "req_003",
  "payload": {
    "items": [
      { "room_id": "msg_1", "text": "Hi there!", "who_sent": 123, "images": [] },
      { "room_id": "msg_2", "text": "Hello!", "who_sent": 456, "images": [] }
    ],
    "total_pages": 2,
    "page": 1,
    "size": 50
  }
}
```
- **REST Alternative (Legacy)**: `GET /v1/conversations/{conversation_id}/messages`

### 4. Exchanging Messages
Messages are sent through the same WebSocket and delivered in real-time regardless of which server instance the users are connected to.

**Sending a Message:**
```json
{
  "type": "SEND_MESSAGE",
  "request_id": "req_004",
  "payload": { "text": "How are you?", "images": [] }
}
```
*Response: `MESSAGE_SENT` event.*

**Receiving a Message (Push):**
The receiver gets a push event immediately:
```json
{
  "type": "MESSAGE",
  "payload": { "room_id": "msg_3", "text": "How are you?", "who_sent": 123, "images": [] }
}
```

---

## 💓 Heartbeat (Keep-Alive)

To prevent stale sessions and maintain the connection, the service uses a **binary heartbeat**.

| Direction | Payload (Hex) | Description |
| :--- | :--- | :--- |
| **Server $\rightarrow$ Client** | `0x01` | **PING**: Sent every 10 seconds. |
| **Client $\rightarrow$ Server** | `0x02` | **PONG**: Must be responded within the timeout window. |

**Failure Logic**: If the server does not receive a `0x02` response, it closes the WebSocket and removes the user's presence from Redis.

---

## 🛠️ Error Handling

All errors are returned with a consistent format:

```json
{
  "type": "ERROR",
  "request_id": "req_xyz",
  "payload": {
    "code": "ERROR_CODE",
    "message": "Human readable explanation"
  }
}
```

**Common Error Codes:**
- `UNKNOWN_EVENT`: The requested event type is not supported.
- `INVALID_JSON`: The payload was not valid JSON.
- `MISSING_CHAT_ID`: Required `chat_id` was not provided.
- `NO_ACTIVE_CHAT`: Tried to send a message without opening a conversation first.
- `EMPTY_MESSAGE`: Tried to send a message with no text and no images.
