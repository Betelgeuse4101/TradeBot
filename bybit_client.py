import aiohttp
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from decimal import Decimal
from logger import get_logger, log_function_call
from constants import BYBIT_API_URLS, BYBIT_API_TIMEOUT, BYBIT_SPOT_CATEGORY
from utils import to_decimal


class BybitClient:
    """
    Клиент для взаимодействия с API биржи Bybit.

    Предоставляет методы для получения рыночных данных:
    - Цены отдельных криптовалют
    - Множественные цены
    - Детальная информация по тикерам
    - Корректное отображение объема (в USDT)
    """

    def __init__(self, cache_ttl: int = 30):
        """
        Инициализирует клиента Bybit.

        Args:
            cache_ttl: Время жизни кэша в секундах
        """
        self.session: Optional[aiohttp.ClientSession] = None
        self.base_urls = BYBIT_API_URLS
        self.current_url_index = 0
        self.request_count = 0
        self.error_count = 0
        self.cache_ttl = cache_ttl
        self.cache: Dict[str, tuple[Dict, datetime]] = {}

        self.logger = get_logger('bybit_client')
        self.logger.debug("🔧 Инициализация Bybit клиента")

    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Создает или возвращает существующую сессию.

        Returns:
            aiohttp.ClientSession: HTTP сессия
        """
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
            self.logger.debug("🔌 Создана новая HTTP сессия")
        return self.session

    def _get_from_cache(self, key: str) -> Optional[Dict]:
        """
        Получает данные из кэша.

        Args:
            key: Ключ кэша

        Returns:
            Optional[Dict]: Данные из кэша или None
        """
        if key in self.cache:
            data, timestamp = self.cache[key]
            if (datetime.now() - timestamp).seconds < self.cache_ttl:
                return data
            else:
                del self.cache[key]
        return None

    def _add_to_cache(self, key: str, data: Dict):
        """
        Добавляет данные в кэш.

        Args:
            key: Ключ кэша
            data: Данные для кэширования
        """
        self.cache[key] = (data, datetime.now())

    def _parse_ticker_data(self, ticker: Dict, symbol: str) -> Dict:
        """
        Парсит данные тикера и преобразует числовые значения в Decimal.
        Специальная обработка для объема (конвертация в USDT).

        Args:
            ticker: Сырые данные тикера
            symbol: Торговый символ

        Returns:
            Dict: Данные с Decimal значениями и корректным объемом
        """
        result = {}

        # Получаем цену для конвертации объема
        last_price = to_decimal(ticker.get('lastPrice', '0'))

        for key, value in ticker.items():
            if key in ['lastPrice', 'highPrice24h', 'lowPrice24h', 'prevPrice24h']:
                result[key] = to_decimal(value)
            elif key == 'volume24h':
                # Объем в количестве монет
                volume_coins = to_decimal(value)
                result['volume_coins'] = volume_coins

                # Конвертируем в USDT (цена * количество монет)
                if last_price and volume_coins:
                    result['volume_usdt'] = volume_coins * last_price
                else:
                    result['volume_usdt'] = Decimal('0')

                # Для обратной совместимости
                result[key] = volume_coins

            elif key == 'price24hPcnt':
                result[key] = to_decimal(value)
            else:
                result[key] = value

        # Логируем реальные данные
        self.logger.info(
            f"📊 РЕАЛЬНЫЕ ДАННЫЕ {symbol}: "
            f"цена=${last_price}, "
            f"объем={result.get('volume_coins'):,.0f} монет, "
            f"объем=${result.get('volume_usdt'):,.0f} USDT"
        )

        return result

    def _validate_ticker_response(self, data: Dict, symbol: str) -> Optional[Dict]:
        """
        Валидирует ответ от API.

        Args:
            data: Данные от API
            symbol: Запрашиваемый символ

        Returns:
            Optional[Dict]: Валидные данные или None
        """
        if data.get("retCode") != 0:
            self.logger.error(f"❌ Ошибка API: {data.get('retMsg', 'Unknown error')}")
            return None

        result = data.get("result", {})
        ticker_list = result.get("list", [])

        if not ticker_list:
            self.logger.warning(f"⚠️ Пустой список тикеров для {symbol}")
            return None

        return self._parse_ticker_data(ticker_list[0], symbol)

    async def _make_request_with_retry(self, url: str, params: Dict,
                                       max_retries: int = 3) -> Optional[Dict]:
        """
        Выполняет HTTP запрос с повторными попытками.

        Args:
            url: URL для запроса
            params: Параметры запроса
            max_retries: Максимальное количество попыток

        Returns:
            Optional[Dict]: Ответ от API или None
        """
        session = await self._get_session()

        for attempt in range(max_retries):
            try:
                async with session.get(url, params=params,
                                       timeout=BYBIT_API_TIMEOUT) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        self.logger.error(f"❌ HTTP ошибка {response.status}, попытка {attempt + 1}")

            except asyncio.TimeoutError:
                self.logger.error(f"⏱️ Таймаут, попытка {attempt + 1}")
            except Exception as e:
                self.logger.error(f"❌ Ошибка запроса: {e}, попытка {attempt + 1}")

            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

        return None

    @log_function_call()
    async def get_ticker(self, symbol: str, use_cache: bool = True) -> Optional[Dict]:
        """
        Получает данные по тикеру для указанного символа.

        Args:
            symbol: Торговый символ (например, "BTCUSDT")
            use_cache: Использовать кэш

        Returns:
            Optional[Dict]: Данные тикера или None
        """
        self.request_count += 1
        self.logger.debug(f"📡 Запрос #{self.request_count} для {symbol}")

        # Проверяем кэш
        if use_cache:
            cached = self._get_from_cache(symbol)
            if cached:
                self.logger.debug(f"✅ Данные для {symbol} получены из кэша")
                return cached

        # Пробуем разные URL
        for attempt in range(len(self.base_urls)):
            url_index = (self.current_url_index + attempt) % len(self.base_urls)
            base_url = self.base_urls[url_index]

            url = f"{base_url}/v5/market/tickers"
            params = {
                "category": BYBIT_SPOT_CATEGORY,
                "symbol": symbol
            }

            self.logger.debug(f"Запрос к {base_url} для {symbol}")

            response = await self._make_request_with_retry(url, params)

            if response:
                ticker_data = self._validate_ticker_response(response, symbol)
                if ticker_data:
                    # Успешный запрос, запоминаем рабочий URL
                    self.current_url_index = url_index

                    # Сохраняем в кэш
                    self._add_to_cache(symbol, ticker_data)

                    return ticker_data

            await asyncio.sleep(1)

        # Если все попытки неудачны - ВОЗВРАЩАЕМ None, а не случайные данные!
        self.error_count += 1
        self.logger.error(f"❌ НЕ УДАЛОСЬ ПОЛУЧИТЬ ДАННЫЕ для {symbol} после всех попыток")
        return None

    @log_function_call()
    async def get_multiple_tickers(self, symbols: List[str],
                                   use_cache: bool = True) -> Dict[str, Dict]:
        """
        Получает данные по нескольким тикерам одновременно.

        Args:
            symbols: Список торговых символов
            use_cache: Использовать кэш

        Returns:
            Dict[str, Dict]: Словарь {символ: данные тикера}
        """
        self.logger.info(f"📊 Запрос данных для {len(symbols)} тикеров")
        results = {}

        # Фильтруем символы, которые можно получить из кэша
        symbols_to_fetch = []
        if use_cache:
            for symbol in symbols:
                cached = self._get_from_cache(symbol)
                if cached:
                    results[symbol] = cached
                else:
                    symbols_to_fetch.append(symbol)
        else:
            symbols_to_fetch = symbols

        if symbols_to_fetch:
            # Создаем задачи для параллельных запросов
            tasks = [self.get_ticker(symbol, use_cache=False) for symbol in symbols_to_fetch]
            tickers = await asyncio.gather(*tasks, return_exceptions=True)

            for symbol, ticker in zip(symbols_to_fetch, tickers):
                if isinstance(ticker, dict) and ticker:
                    results[symbol] = ticker
                elif isinstance(ticker, Exception):
                    self.logger.error(f"❌ Ошибка при получении {symbol}: {ticker}")
                else:
                    self.logger.error(f"❌ Не удалось получить данные для {symbol}")

        self.logger.info(f"✅ Получено {len(results)} из {len(symbols)} тикеров")
        return results

    # УДАЛЯЕМ метод _get_mock_ticker() полностью!

    async def get_stats(self) -> Dict[str, Any]:
        """
        Возвращает статистику работы клиента.

        Returns:
            Dict: Статистика
        """
        success_rate = 0
        if self.request_count > 0:
            success_rate = (self.request_count - self.error_count) / self.request_count * 100

        return {
            'total_requests': self.request_count,
            'error_count': self.error_count,
            'success_rate': round(success_rate, 2),
            'cache_size': len(self.cache),
            'current_url': self.base_urls[self.current_url_index]
        }

    async def close(self):
        """
        Закрывает HTTP сессию.
        """
        if self.session and not self.session.closed:
            await self.session.close()
            self.logger.info(
                f"🔌 Сессия Bybit закрыта. "
                f"Всего запросов: {self.request_count}, ошибок: {self.error_count}"
            )


# Создаем глобальный экземпляр
bybit_client = BybitClient()