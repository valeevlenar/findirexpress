import os
from aiogram import Bot
from dotenv import load_dotenv

load_dotenv()

support_bot = Bot(token=os.getenv('SUPPORTBOTTOKEN'))