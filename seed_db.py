import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from repository import ConversationRepository
from model import Conversation
from config import MONGODB_URL
import uuid

async def seed():
    client = AsyncIOMotorClient(MONGODB_URL)
    repo = ConversationRepository(client, "maintenance_service")
    
    # Create a test conversation for user 1
    conv = Conversation(
        conversation_id=str(uuid.uuid4()),
        name="Welcome Chat",
        people=[1]
    )
    
    await repo.add(conv)
    print(f"Successfully created conversation: {conv.conversation_id}")

if __name__ == "__main__":
    import uuid
    asyncio.run(seed())
