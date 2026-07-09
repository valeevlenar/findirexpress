import logging
from tenacity import (wait_combine,
    retry,
    wait_exponential,
    stop_after_attempt,
    retry_if_exception_type,
    wait_chain,
    wait_fixed)
from tenacity import RetryCallState
from tenacity.wait import wait_base
import aiohttp
import asyncio
from datetime import datetime, timedelta
from aiohttp import TCPConnector

from app.database.api_functions import unauthorised_api_identified


class WaitRateLimitAfter(wait_base):
    def __call__(self, retry_state: RetryCallState) -> float:
        if retry_state.outcome and retry_state.outcome.failed:
            exc = retry_state.outcome.exception()
            if isinstance(exc, RateLimitError):
                return float(exc.retry_after)
        return 0.0

class ApiError(Exception):
    """Кастомная ошибка API"""
    def __init__(self, status_code, message):
        self.status_code = status_code
        self.message = message
        super().__init__(f"API Error {status_code}: {message}")

class UnauthorizedError(ApiError):
    def __init__(self):
        super().__init__(401, "Unauthorized")

class RateLimitError(ApiError):
    """Кастомная ошибка для лимита запросов"""
    def __init__(self, retry_after: int):
        super().__init__(429, "Rate limit exceeded")
        self.retry_after = retry_after
        self.wait_until = datetime.now() + timedelta(seconds=retry_after)

async def before_sleep_handler(retry_state):
    """Обработчик перед повторной попыткой"""
    if retry_state.outcome.failed:
        exc = retry_state.outcome.exception()
        if isinstance(exc, RateLimitError):
            wait_time = exc.retry_after
            logging.warning(f"Rate limited. Waiting {wait_time} seconds until {exc.wait_until}")
            await asyncio.sleep(wait_time)

class ApiClient:
    """Универсальный клиент для работы с API"""

    def __init__(self, db_session=None, seller_id=None, api_key=None):
        self._session = None
        self._default_timeout = 30
        self.db_session = db_session
        self.seller_id = seller_id
        self.api_key = api_key

    async def close_session(self):
        if self._session and not self._session.closed:
            try:
                await self._session.close()
            except Exception as e:
                logging.error(f"Error closing session: {str(e)}")
            finally:
                self._session = None

    async def __aenter__(self):
        connector = TCPConnector(limit=100)  # Максимум 10 соединений
        self._session = aiohttp.ClientSession(connector=connector)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_session()

    async def fetch(
            self,
            method: str,
            url: str,
            headers: dict = None,
            params: dict = None,
            data: dict = None,
            json: dict = None,
            timeout: int = None
    ):
        @retry(wait=wait_chain(
        WaitRateLimitAfter(),  # Кастомная задержка для 429
        wait_exponential(multiplier=2, max=30)  # Экспоненциальный backoff
        ),
        stop=stop_after_attempt(20),
        retry=(
        retry_if_exception_type(RateLimitError) |
        retry_if_exception_type(aiohttp.ClientError) |
        retry_if_exception_type(asyncio.TimeoutError)
        ),
        before_sleep=before_sleep_handler
        )

        async def _fetch():

            # Универсальный метод для выполнения запросов
            # :param method: HTTP метод (GET/POST/PUT/DELETE)
            # :param url: URL эндпоинта
            # :param headers: Заголовки запроса
            # :param params: Query параметры (для GET)
            # :param data: Form-encoded данные (для POST)
            # :param json: JSON данные (для POST/PUT)
            # :param timeout: Таймаут запроса

            kwargs = {
                "headers": headers or {},
                "params": params,
                "data": data,
                "json": json,
                "timeout": aiohttp.ClientTimeout(total=timeout or self._default_timeout)
            }

            try:
                async with self._session.request(method.upper(), url, **kwargs) as response:
                    logging.info(f'Seller_id: {self.seller_id}. Api response: {response.status}')
                    await self._validate_response(response)
                    return await self._parse_response(response)

            except UnauthorizedError as e:
                # Вызываем обработчик авторизации и повторяем запрос
                if self.db_session and self.seller_id and self.api_key:
                    await unauthorised_api_identified(
                        self.db_session,
                        self.seller_id,
                        self.api_key
                    )
                raise

            except RateLimitError:
                # ОБЯЗАТЕЛЬНО пробрасываем ошибку лимита дальше, чтобы tenacity её поймал!
                raise

            except aiohttp.ClientError as e:
                logging.error(f"Connection error: {str(e)}")
                raise

            except Exception as e:
                # Ловим всё остальное, логируем, но ТОЖЕ пробрасываем дальше (raise)
                logging.error(f'Seller_id: {self.seller_id}. Request failed with error: {e}')
                raise

        return await _fetch()

    async def _validate_response(self, response):
        """Обработка статус-кодов"""
        if response.status == 429:
            # WB использует нестандартные заголовки, проверяем их все
            retry_after = response.headers.get("Retry-After") or \
                          response.headers.get("X-Ratelimit-Retry") or \
                          response.headers.get("X-Ratelimit-Reset") or 60

            logging.info(f'Seller_id: {self.seller_id}. Поймали 429. Ждем {retry_after} сек и перезапускаем.')
            raise RateLimitError(int(retry_after))

        elif response.status == 401:
            logging.info(f'Seller_id: {self.seller_id}. Неавторизованный api-ключ.')
            raise UnauthorizedError()

        elif response.status >= 400:
            error_text = await response.text()
            logging.info(f'Seller_id: {self.seller_id}. Ошибка в апи-выгрузке: {error_text}')
            raise ApiError(response.status, error_text)

    async def _parse_response(self, response):
        """Парсинг ответа с автоматическим определением формата"""
        content_type = response.headers.get('Content-Type', '')

        if 'application/json' in content_type:
            return await response.json()
        if 'text/plain' in content_type:
            return await response.text()
        if 'octet-stream' in content_type:
            return await response.read()

        return await response.text()
