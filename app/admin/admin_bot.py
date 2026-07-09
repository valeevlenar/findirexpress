import os
from aiogram import Bot
from dotenv import load_dotenv

load_dotenv()

admin_bot = Bot(token=os.getenv('ADMINBOTTOKEN'))