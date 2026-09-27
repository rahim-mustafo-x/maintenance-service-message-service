from dotenv import load_dotenv
from os import getenv

load_dotenv()

PORT = int(getenv('PORT',7877))
EUREKA_URL = getenv('EUREKA_URL')
APP_NAME='message-service'
JWT_SECRET_KEY = getenv('JWT_SECRET_KEY')