# Ktor Chat Service Migration Specification

## Purpose

Prepare a production-minded Kotlin/Ktor implementation of the existing Python FastAPI chat service. Preserve the currently working behavior and all existing chat history for users such as user1 and user2.

This file is the implementation brief for the coding assistant. Read the current repository and service contracts before changing code. Do not assume undocumented API shapes.

## Non-negotiable data safety

- The existing MongoDB database is `maintenance_service`.
- Existing collections are `conversations` and `rooms`.
- Existing direct conversation IDs use the format `direct-{lowerUserId}-{higherUserId}`, for example `direct-1-2`.
- Conversation documents contain fields such as `conversation_id`, `name`, `profile_image`, `people`, and `updated_at`.
- Room/message documents contain fields such as `room_id`, `conversation_id`, `text`, `who_sent`, `images`, and `created_at`.
- The canonical image field is `images: List<String>`, containing absolute image URLs returned by Image Service. Legacy documents may have no image or edit/delete metadata.
- New optional lifecycle fields are `is_edited` (default false), `is_deleted` (default false), `updated_at`, and `deleted_at`. Read old records without requiring a destructive schema migration.
- A message may contain text, one or more image URLs, or both. An image-only message is valid. Never persist raw image bytes/base64 in the chat document.
- **Never drop the database or collections, truncate collections, or delete/recreate existing conversations as part of migration.**
- Do not run automatic destructive migrations. Any data migration must be backward-compatible, idempotent, explicitly reviewed, and preceded by a verified backup.
- Preserve existing user1/user2 conversation IDs and all historical message documents. New code must read the existing document shape.
- Do not report deployment or tests as successful unless actually run and verified.

## Desired stack

- Kotlin + Ktor server.
- Ktor WebSockets for real-time messaging.
- MongoDB for durable conversations and messages.
- Redis for online presence, active websocket ownership, heartbeat TTL, and optional short-lived profile cache.
- Eureka integration / existing service-discovery mechanism where required by the current deployment.
- Existing USER-SERVICE remains the source of truth for user identity and profile information.
- Use kotlinx.serialization (or the serialization library already selected by the project) consistently for wire payloads.

Inspect the existing project and dependency versions first. Do not upgrade unrelated dependencies or introduce a second competing architecture without a reason.

## User identity and display names

1. Authenticate each websocket connection using the existing access-token contract.
2. Derive the authenticated `userId` from the validated token. Never trust a user ID sent in a client payload as the authenticated identity.
3. Use the bearer token to request the user's profile from USER-SERVICE through the configured service discovery/network path.
4. Resolve and retain the profile's display name (for example, `fullName`) and avatar metadata in the in-memory websocket session. Do not store the raw access token in MongoDB or Redis.
5. Redis presence may store only necessary metadata such as `userId`, `displayName`, optional avatar URL, `sessionId`, connection status, and TTL. Do not put bearer tokens, passwords, or other secrets in presence values or logs.
6. Heartbeats should refresh presence/session TTL and confirm that the connection still owns the user's active session. Do not call USER-SERVICE on every heartbeat. Resolve the profile at connection time and refresh it on reconnect or via a bounded cache TTL.
7. Offline users must still have names in conversation lists. Conversation display names must not depend on the other participant being online.
8. For a direct conversation, find the other participant by excluding the authenticated user's ID from `people`, then resolve that participant's profile from USER-SERVICE or a bounded profile cache. Never display a shared conversation `name` as if it were correct for both participants.
9. If USER-SERVICE is temporarily unavailable, use a previously cached profile or a safe fallback such as `User {id}`. Do not fail to load durable message history solely because profile lookup failed.

## MongoDB persistence rules

- Every accepted message must be inserted into MongoDB before the server emits a success acknowledgement or broadcasts it as successfully persisted.
- If the MongoDB write fails, return a structured error. Do not send a success acknowledgement, and do not clear the user's draft in the client.
- Persist at least: `room_id`, `conversation_id`, `text`, `who_sent`, `images`, and `created_at`, matching the current schema.
- Update the conversation's `updated_at` only after the message insert succeeds.
- Use server-side authenticated `userId` as `who_sent`; ignore or reject a client-supplied sender ID.
- Confirm that the authenticated user is a participant in the target conversation before reading history or sending a message.
- Use stable, deterministic direct conversation IDs for each unique pair of participants. Prevent self-chat unless product requirements explicitly change.
- Make conversation creation race-safe. Two simultaneous requests for the same pair must not create duplicate direct conversations. Use an appropriate unique index/upsert after checking existing data; index creation must not destroy or rewrite records.
- Paginate history in a deterministic order using `created_at` and a stable tie-breaker such as `room_id`. Document whether page 1 is newest-first or oldest-first and keep client behavior consistent.
- Do not assume MongoDB database name from the old `.env` URI path. The current live chat records were found in `maintenance_service`, while the URI path previously pointed at `message_database`. Configure the database explicitly and verify it against the existing deployment before rollout.
- Reuse existing collections and field names unless an explicit backward-compatible migration is approved.

## Redis presence and one websocket per user

- Maintain one active websocket session per user if that is the existing product rule.
- Claim a session atomically (for example, a Redis Lua script or another atomic compare-and-set design) so concurrent connections cannot both become active.
- Store a unique `sessionId` and a TTL for presence. Heartbeat refreshes TTL only if the session still owns the user's presence key.
- When a new connection supersedes an old one, close the old websocket if possible. The old connection must not delete or overwrite the new session during its disconnect cleanup.
- Disconnect cleanup must be conditional: delete presence only when the stored `sessionId` matches the disconnecting session.
- Handle missed heartbeats, Redis errors, websocket disconnects, reconnects, and server shutdown safely.
- Presence is ephemeral. MongoDB conversation/message history is durable and must never be deleted when presence expires.

## WebSocket protocol compatibility

Keep existing event names and payload shape compatible with the current client unless a versioned protocol change is explicitly made. Inspect the actual current protocol and `WEBSOCKET_PROTOCOL.md` before implementing.

At minimum, preserve the equivalent behavior for:
- `LIST_CONVERSATIONS`
- `OPEN_CONVERSATION`
- `GET_HISTORY`
- `SEND_MESSAGE`
- `CONVERSATIONS_LIST`
- `CONVERSATION_OPENED`
- `MESSAGES_PAGE`
- `MESSAGE_SENT`
- `MESSAGE`
- `ERROR`

Requirements:
- Echo the request ID on responses.
- Use a unique request ID for each request; never reuse a constant ID such as `req_send`.
- Serialize dates to ISO-8601 JSON safely.
- A late history response from a previously selected chat must not overwrite the currently selected chat.
- A message from a different conversation must never be appended to the selected conversation.
- Avoid rendering the sender's own message twice when both an acknowledgement and a broadcast exist.
- Do not acknowledge persistence before MongoDB insert completion.
- Validate event type, payload shape, text length, image references, pagination bounds, and conversation membership. Return structured errors instead of crashing the websocket loop.

## Message edit/delete and image URL contract

- Preserve `images: List<String>` as the canonical persisted and WebSocket field because existing history already uses this shape.
- For backward/client convenience, SEND_MESSAGE may accept either `images: [url, ...]` or a single `image_url: url`; normalize both to the stored `images` array.
- Image URLs must be absolute HTTP/HTTPS URLs, with a documented maximum of 10 images per message. Upload bytes through IMAGE-SERVICE; Message Service only stores URL references.
- A message is valid when it has non-blank text OR at least one valid image URL. Image-only messages must work.
- Add authenticated REST endpoints: `PATCH /v1/messages/{message_id}` and `DELETE /v1/messages/{message_id}`.
- PATCH accepts optional `text`, `images`, or `image_url`; omitted fields remain unchanged. Validate the final message still has text or at least one image.
- Only the authenticated message author may edit or delete. Verify conversation membership against `maintenance_service.conversations`; never trust a sender ID supplied by the client.
- DELETE should be a soft delete: set `is_deleted=true`, set `deleted_at` and `updated_at`, and clear visible `text` and `images`. History must render a deleted-message placeholder rather than failing to deserialize the old record.
- After the MongoDB write succeeds, publish `message.updated` or `message.deleted` through Redis Pub/Sub and WebSocket to connected participants currently viewing that conversation. Never broadcast before persistence succeeds.
- Existing `MESSAGE` send broadcasts must remain compatible. New event names are `message.updated` and `message.deleted`; preserve `room_id`, `conversation_id`, and request/response correlation where applicable.
- The Ktor implementation must share these exact semantics and wire fields, not invent a second `imageUrl`/attachment model.

## REST/API compatibility

Inspect current endpoints and keep compatible routes and response fields where possible, including the existing conversation list, paginated messages, user search, and direct-conversation creation endpoints. Preserve the current authentication expectations and USER-SERVICE response handling. Do not guess USER-SERVICE JSON fields; verify the actual DTOs and API responses in the repository.

## Suggested Kotlin design

Use clear separation of concerns without overengineering:

- `AuthService`: validate token / resolve authenticated user identity using the project's established auth approach.
- `UserProfileClient`: call USER-SERVICE and map its response to a small internal `UserProfile` DTO.
- `PresenceRepository`: Redis presence, atomic session claim, heartbeat TTL refresh, conditional cleanup.
- `ConversationRepository`: MongoDB conversation reads and race-safe direct conversation creation.
- `MessageRepository`: MongoDB message insertion and paginated history reads.
- `ChatService`: authorization and use-case orchestration.
- `ChatWebSocketHandler`: protocol parsing, request correlation, response serialization, and connection lifecycle.
- Typed Kotlin DTOs for requests, responses, profile data, conversations, and messages.
- Reuse one configured MongoDB/Redis client per application lifecycle. Do not create a new database client for every websocket event.
- Use structured logging with user/session IDs where appropriate, but never log bearer tokens or full sensitive message contents.

Follow existing project conventions if they already provide equivalent components. Do not create duplicate repositories/services.

## Failure handling

- USER-SERVICE down: retain history access; use cache or `User {id}` fallback for names.
- Redis unavailable: fail connection/session claim safely according to the current availability policy; never corrupt MongoDB history.
- MongoDB unavailable during send: return an error and do not acknowledge the message as saved.
- Websocket disconnect: clear only the current session's presence; preserve all MongoDB documents.
- Invalid or expired token: reject the connection with the existing authentication behavior.
- Malformed websocket frame: return a structured error and keep the connection alive when safe.
- Duplicate/retried send: do not create duplicate messages if the protocol supports a client message ID; otherwise document the delivery semantics and avoid claiming exactly-once delivery.

## Required tests before rollout

### Unit tests
- Parse/authenticate a valid token and reject an invalid token.
- Determine the peer in a two-person conversation for both participants.
- Profile lookup maps the actual USER-SERVICE response correctly.
- Heartbeat refreshes TTL only for the current session.
- Old session cleanup cannot delete a newer session's presence.
- MongoDB failure produces an error and no success acknowledgement.
- Image-only message is accepted and persisted with `text=null` and a non-empty `images` array.
- Invalid/non-HTTP image URLs and more than 10 images are rejected.
- An existing text-only message remains compatible with `images=[]`.
- Only the author can PATCH or DELETE; other participants receive 403.
- PATCH preserves fields omitted from the request and rejects a final empty message.
- DELETE clears visible content, sets tombstone fields, and publishes `message.deleted` only after MongoDB succeeds.
- PATCH publishes `message.updated` only after MongoDB succeeds.
- History serialization emits valid ISO-8601 timestamps.

### Integration tests
- Existing `direct-1-2` conversation is read without changing its ID.
- Existing messages in `rooms` remain readable after Ktor starts.
- Send a message as user1; confirm it is stored in MongoDB before acknowledgement.
- Refresh/reconnect as user1; the message remains in history.
- Sign in as user2; the same message appears in the same conversation.
- Send a reply as user2; user1 sees it without duplicates.
- Each user sees the other participant's correct display name.
- Two simultaneous create-conversation requests for the same pair result in one conversation.
- Rapidly switch between two chats; late responses/messages do not appear in the wrong chat.
- Disconnect and reconnect; old cleanup does not remove the new presence.
- Expired presence does not delete conversations or messages.

## Migration and rollout plan

1. Inspect current Python service code, current client protocol, USER-SERVICE DTOs, Redis presence implementation, and deployment configuration.
2. Confirm the live database/collection names and compare the current MongoDB document shape with the Kotlin DTOs. Read-only inspection first.
3. Create and verify a backup of the correct `maintenance_service` database before any rollout that might change persistence or schema.
4. Implement Ktor against the existing schema. Do not drop or clear collections.
5. Run unit and integration tests against a separate test database first.
6. Deploy to a staging environment or a separate port/service if available.
7. Verify user1/user2 history, profile names, sends, reconnects, and one-session-per-user behavior.
8. Switch traffic only after checks pass; retain a rollback path to the Python service.
9. Monitor logs and MongoDB counts before removing any old service. Do not delete old data as part of deployment.

## Definition of done

- [ ] Existing user1/user2 history remains visible and unchanged.
- [ ] All accepted messages are persisted before success acknowledgements.
- [ ] Text-only, image-only, and text-plus-image messages are supported with the legacy `images` URL array.
- [ ] PATCH/DELETE enforce author and conversation authorization and broadcast events only after persistence.
- [ ] Refresh/reconnect reloads history from MongoDB.
- [ ] Correct peer name is displayed for both participants, online or offline.
- [ ] Heartbeat and Redis presence correctly enforce one active websocket per user.
- [ ] Expired or replaced sessions cannot delete current presence.
- [ ] No raw tokens are stored in MongoDB/Redis or logs.
- [ ] REST and websocket contracts remain compatible with the current client.
- [ ] Tests pass and deployment is verified with actual logs and end-to-end checks.
- [ ] No destructive database cleanup occurred.
