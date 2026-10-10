import sys
from py_eureka_client.eureka_client import init_async, stop_async
from config import (APP_NAME, PORT, EUREKA_URL)
from asyncio import (gather, run)
from uvicorn import (Config, Server)
from apis import app

async def main():
    await init_async(
        eureka_server=EUREKA_URL,
        app_name=APP_NAME,
        instance_port=PORT
    )

    # Start background listener for Redis broadcasts
    asyncio.create_task(
        service.message_members_manager.listen_for_broadcasts(service.presence)
    )

    config = Config(app=app, host='0.0.0.0', port=PORT)
    server = Server(config=config)
    try:
        await gather(server.serve())
    finally:
        await stop_async()
if __name__ == '__main__':
    try:
        run(main())
    except KeyboardInterrupt:
        sys.exit(0)
