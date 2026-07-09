# -*- coding: utf-8 -*-
import logging
from logging import FileHandler
from logging.handlers import RotatingFileHandler
from logging.handlers import TimedRotatingFileHandler

class InfoFilter(logging.Filter):
    """Пропускает только сообщения уровня INFO"""
    def filter(self, record):
        return record.levelno == logging.INFO

class NotInfoFilter(logging.Filter):
    """Исключает сообщения уровня INFO"""
    def filter(self, record):
        return record.levelno != logging.INFO

def setup_logging():
    # Настройка основного логгера
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Очищаем finbot_log.log при каждом запуске
    with open('finbot_log.log', 'w') as f:
        pass  # Очистка файла

    # Форматтер для всех обработчиков
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(funcName)s: %(lineno)d - %(message)s"
    )

    # Обработчик для INFO (info.log)
    info_handler = TimedRotatingFileHandler(
        'info.log',
        when='midnight',  # ротация каждый день
        interval=1,
        backupCount=14,  # хранить 14 дней
        encoding='UTF-8'
    )
    info_handler.setLevel(logging.INFO)
    info_handler.addFilter(InfoFilter())
    info_handler.setFormatter(formatter)

    # Обработчик для остальных уровней (finbot_log.log)
    error_handler = TimedRotatingFileHandler(
        'finbot_log.log',
        when='midnight',  # ротация каждый день
        interval=1,
        backupCount=14,  # хранить 14 дней
        encoding='UTF-8'
    )
    error_handler.setLevel(logging.WARNING)
    # error_handler.addFilter(NotInfoFilter()) #не нужен, если стоит уровень warning
    error_handler.setFormatter(formatter)

    # Добавляем обработчики
    logger.addHandler(info_handler)
    logger.addHandler(error_handler)

    logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)

    # Отключаем логирование для сторонних библиотек
    logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)

    # Отключаем стандартный StreamHandler
    logging.getLogger().addHandler(logging.NullHandler())