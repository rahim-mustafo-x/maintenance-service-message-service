from dotenv import load_dotenv
from os import getenv

load_dotenv()

PORT = int(getenv('PORT',7877))
EUREKA_URL = getenv('EUREKA_URL')
APP_NAME='message-service'
JWT_SECRET_KEY = getenv('JWT_SECRET_KEY')
MONGODB_URL = getenv('MONGODB_URL')
REDIS_HOST = getenv('REDIS_HOST')
REDIS_PORT = int(getenv("REDIS_PORT") or "6379")

#for ping-pong
PING = b"\x01"
PONG = b"\x02"
# Internal Image Service URL on maintenance-net.
IMAGE_SERVICE_URL = getenv("IMAGE_SERVICE_URL", "http://image-service:7878").rstrip("/")
# Public gateway base including /image-service; optional override.
IMAGE_PUBLIC_BASE_URL = getenv("IMAGE_PUBLIC_BASE_URL", "").rstrip("/")
