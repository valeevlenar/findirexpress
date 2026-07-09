import asyncio

# Создаем семафор с ограничением в 10 одновременных задач
semaphore = asyncio.Semaphore(15)