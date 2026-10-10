from typing import (
    TypeVar,
    Generic,
    Type,
    List,
    Any,
    Optional,
)

from motor.motor_asyncio import AsyncIOMotorClient

from pydantic import BaseModel

from model import (
    Page,
    Conversation,
    Room,
    User
)


T = TypeVar(
    "T",
    bound=BaseModel
)


class BaseMongoRepository(
    Generic[T]
):

    def __init__(
        self,
        client: AsyncIOMotorClient,
        db_name: str,
        collection_name: str,
        model_class: Type[T],
        id_field: str,
    ):

        self.db = client[db_name]

        self.collection = self.db[
            collection_name
        ]

        self.model_class = model_class

        self.id_field = id_field

    # -------------------------
    # CREATE
    # -------------------------

    async def add(
        self,
        item: T
    ) -> str:

        data = item.model_dump()

        entity_id = getattr(
            item,
            self.id_field
        )

        data["_id"] = entity_id

        await self.collection.insert_one(
            data
        )

        return entity_id

    # -------------------------
    # UPDATE
    # -------------------------

    async def update_fields(
        self,
        entity_id: str,
        updates: dict[str, Any],
    ) -> bool:

        result = await self.collection.update_one(
            {"_id": entity_id},
            {
                "$set": updates
            }
        )

        return result.modified_count > 0

    # -------------------------
    # REMOVE FIELDS
    # -------------------------

    async def remove_fields(
        self,
        entity_id: str,
        fields_to_remove: List[str],
    ) -> bool:

        unset_dict = {
            field: ""
            for field in fields_to_remove
        }

        result = await self.collection.update_one(
            {"_id": entity_id},
            {
                "$unset": unset_dict
            }
        )

        return result.modified_count > 0

    # -------------------------
    # DELETE
    # -------------------------

    async def delete(
        self,
        entity_id: str
    ) -> bool:

        result = await self.collection.delete_one(
            {
                "_id": entity_id
            }
        )

        return result.deleted_count > 0

    # -------------------------
    # GET BY ID
    # -------------------------

    async def get_by_id(
        self,
        entity_id: str
    ) -> Optional[T]:

        document = await self.collection.find_one(
            {
                "_id": entity_id
            }
        )

        if document is None:
            return None

        return self.model_class(
            **document
        )

    # -------------------------
    # PAGE
    # -------------------------

    async def get_page(
        self,
        query: dict,
        page: int,
        size: int,
    ) -> Page[T]:

        if page < 1:
            page = 1

        if size < 1:
            size = 10

        skips = size * (
            page - 1
        )

        total_items = await self.collection.count_documents(query)

        total_pages = (
            (total_items + size - 1) // size
            if total_items > 0
            else 0
        )

        cursor = self.collection.find(query).skip(skips).limit(size)

        items_list = []
        async for document in cursor:
            items_list.append(self.model_class(**document))

        return Page(
            items=items_list,
            total_pages=total_pages,
            page=page,
            size=size,
        )


# =========================================================
# USER REPOSITORY
# =========================================================

class UserRepository(
    BaseMongoRepository[User]
):

    def __init__(
        self,
        client: AsyncIOMotorClient,
        db_name: str,
    ):

        super().__init__(
            client,
            db_name,
            "users",
            User,
            "user_id",
        )

    async def search_users(
        self,
        query: str,
        page: int = 1,
        size: int = 10,
    ) -> Page[User]:
        # Search by name or email using a case-insensitive regex
        search_query = {
            "$or": [
                {"name": {"$regex": query, "$options": "i"}},
                {"email": {"$regex": query, "$options": "i"}},
            ]
        }
        return await self.get_page(
            query=search_query,
            page=page,
            size=size,
        )

# =========================================================
# ROOM / MESSAGE REPOSITORY
# =========================================================

class RoomRepository(
    BaseMongoRepository[Room]
):

    def __init__(
        self,
        client: AsyncIOMotorClient,
        db_name: str,
    ):

        super().__init__(
            client,
            db_name,
            "rooms",
            Room,
            "room_id",
        )

    async def get_messages(
        self,
        conversation_id: str,
        page: int,
        size: int,
    ) -> Page[Room]:

        if page < 1:
            page = 1
        if size < 1:
            size = 10
        query = {"conversation_id": conversation_id}
        skips = size * (page - 1)
        total_items = await self.collection.count_documents(query)
        total_pages = (total_items + size - 1) // size if total_items else 0
        cursor = self.collection.find(query).sort("created_at", 1).skip(skips).limit(size)
        items = []
        async for document in cursor:
            items.append(self.model_class(**document))
        return Page(items=items, total_pages=total_pages, page=page, size=size)


# =========================================================
# CONVERSATION REPOSITORY
# =========================================================

class ConversationRepository(
    BaseMongoRepository[Conversation]
):

    def __init__(
        self,
        client: AsyncIOMotorClient,
        db_name: str,
    ):

        super().__init__(
            client,
            db_name,
            "conversations",
            Conversation,
            "conversation_id",
        )

    async def get_conversations_by_user(
        self,
        user_id: int,
        page: int,
        size: int,
    ) -> Page[Conversation]:

        if page < 1:
            page = 1
        if size < 1:
            size = 10

        # This service's conversation list is for one-to-one chats only.
        query = {"$and": [{"people": user_id}, {"people": {"$size": 2}}]}
        skips = size * (page - 1)
        total_items = await self.collection.count_documents(query)
        total_pages = (total_items + size - 1) // size if total_items else 0
        cursor = self.collection.find(query).sort("updated_at", -1).skip(skips).limit(size)

        items = []
        async for document in cursor:
            items.append(self.model_class(**document))

        return Page(
            items=items,
            total_pages=total_pages,
            page=page,
            size=size,
        )

    async def create_conversation(
        self,
        conversation: Conversation,
    ) -> str:
        return await self.add(conversation)