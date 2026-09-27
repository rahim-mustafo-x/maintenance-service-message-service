#this file is done with the help of AI, by considering the only field for AI to write i personally take the matters into own hand and try not to use AI for the next project where pageable and mongodb is included

from typing import TypeVar, Generic, Type, List, Any
from pymongo import MongoClient
from pydantic import BaseModel
from model import Page, Conversation, Room

T = TypeVar('T', bound=BaseModel)


class BaseMongoRepository(Generic[T]):
    def __init__(self, client: MongoClient, db_name: str, collection_name: str, model_class: Type[T], id_field: str):
        self.db = client[db_name]
        self.collection = self.db[collection_name]
        self.model_class = model_class
        self.id_field = id_field  # e.g., 'room_id' or 'conversation_id'

    # Add a new document
    def add(self, item: T) -> str:
        data = item.model_dump()
        entity_id = getattr(item, self.id_field)
        data["_id"] = entity_id
        self.collection.insert_one(data)
        return entity_id

    # Update or add specific fields in a document
    def update_fields(self, entity_id: str, updates: dict[str, Any]) -> bool:
        result = self.collection.update_one(
            {"_id": entity_id},
            {"$set": updates}
        )
        return result.modified_count > 0

    # Remove specific fields from a document
    def remove_fields(self, entity_id: str, fields_to_remove: List[str]) -> bool:
        # Converts ['text', 'images'] into {'text': "", 'images': ""} for MongoDB $unset
        unset_dict = {field: "" for field in fields_to_remove}
        result = self.collection.update_one(
            {"_id": entity_id},
            {"$unset": unset_dict}
        )
        return result.modified_count > 0

    # Delete an entire document
    def delete(self, entity_id: str) -> bool:
        result = self.collection.delete_one({"_id": entity_id})
        return result.deleted_count > 0

    # Generic Pageable Method
    def get_page(self, query: dict, page: int, size: int) -> Page[T]:
        skips = size * (page - 1)

        total_items = self.collection.count_documents(query)
        total_pages = (total_items + size - 1) // size if total_items > 0 else 0

        cursor = self.collection.find(query).skip(skips).limit(size)
        items_list = [self.model_class(**doc) for doc in cursor]

        return Page(
            items=items_list,
            total_pages=total_pages,
            page=page,
            size=size
        )

class RoomRepository(BaseMongoRepository[Room]):
    def __init__(self, client: MongoClient, db_name: str):
        super().__init__(client, db_name, "rooms", Room, "room_id")


class ConversationRepository(BaseMongoRepository[Conversation]):
    def __init__(self, client: MongoClient, db_name: str):
        super().__init__(client, db_name, "conversations", Conversation, "conversation_id")

    # Custom Search: MongoDB automatically checks if a value exists inside an array
    def get_conversations_by_user(self, user_id: int, page: int, size: int) -> Page[Conversation]:
        query = {"people": user_id}
        return self.get_page(query=query, page=page, size=size)
