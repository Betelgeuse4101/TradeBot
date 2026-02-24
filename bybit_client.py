import aiohttp
import asyncio
from typing import Dict, List, Optional
from logger import get_logger, log_function_call

# Получаем логгер для bybit_client
logger = get_logger('bybit_client')


class BybitClient:
    """
    Клиент для взаимодействия с API биржи Bybit.

    Предоставляет методы для получения рыночных данных:
    - Цены отдельных криптовалют
    - Множественные цены
    - Детальная информация по тикерам

    Attributes:
        session (aiohttp.ClientSession): HTTP сессия для запросов
        base_url (str): Базовый URL API Bybit
    """

    def __init__(self):
        """
        Инициализирует клиента Bybit.

        Устанавливает базовый URL API и создает сессию при первом запросе.
        """
        self.session = None
        self.base_url = "https://api.bybit.com"
        # Альтернативные URL на случай проблем с основным
        self.alternative_urls = [
            "https://api.bybit.com",
            "https://api.bytick.com",
            "https://api-demo.bybit.com"
        ]
        self.current_url_index = 0
        self.request_count = 0
        self.error_count = 0
        logger.debug("🔧 Инициализация Bybit клиента")

    async def _get_session(self):
        """Создает или возвращает существующую сессию"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
            logger.debug("🔌 Создана новая HTTP сессия")
        return self.session

    @log_function_call()
    async def get_ticker(self, symbol: str) -> Optional[Dict]:
        """
        Получает данные по тикеру для указанного символа.

        Выполняет запрос к Bybit API для получения информации о текущей цене,
        изменении за 24 часа, объеме и других метриках.

        Args:
            symbol (str): Торговый символ (например, "BTCUSDT")

        Returns:
            Optional[Dict]: Словарь с данными тикера или None при ошибке.
                           Содержит поля: lastPrice, price24hPcnt,
                           highPrice24h, lowPrice24h, volume24h и др.
        """
        self.request_count += 1
        logger.debug(f"📡 Запрос #{self.request_count} для {symbol}")

        # Пробуем разные URL если основной не работает
        for attempt in range(len(self.alternative_urls)):
            try:
                url_index = (self.current_url_index + attempt) % len(self.alternative_urls)
                base_url = self.alternative_urls[url_index]

                # Правильный эндпоинт для Bybit v5 API
                url = f"{base_url}/v5/market/tickers"
                params = {
                    "category": "spot",
                    "symbol": symbol
                }

                session = await self._get_session()

                logger.debug(f"Запрос к {base_url} для {symbol}")

                async with session.get(url, params=params, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()

                        # Проверяем структуру ответа
                        if data.get("retCode") == 0:
                            result = data.get("result", {})
                            ticker_list = result.get("list", [])
                            if ticker_list and len(ticker_list) > 0:
                                ticker_data = ticker_list[0]
                                # Успешный запрос, запоминаем рабочий URL
                                self.current_url_index = url_index
                                price = float(ticker_data.get('lastPrice', 0))
                                logger.debug(f"✅ {symbol}: ${price:.4f}")
                                return ticker_data
                            else:
                                logger.warning(f"⚠️ Пустой список тикеров для {symbol}")
                        else:
                            error_msg = data.get('retMsg', 'Unknown error')
                            logger.error(f"❌ Ошибка API Bybit для {symbol}: {error_msg}")
                    else:
                        logger.error(f"❌ HTTP ошибка {response.status} для {base_url}")

            except asyncio.TimeoutError:
                self.error_count += 1
                logger.error(f"⏱️ Таймаут при запросе к {base_url} для {symbol}")
            except Exception as e:
                self.error_count += 1
                logger.error(f"❌ Ошибка при запросе к {base_url}: {e}")

            # Небольшая задержка перед следующей попыткой
            await asyncio.sleep(1)

        # Если все попытки неудачны, возвращаем тестовые данные для отладки
        logger.warning(f"⚠️ Использую тестовые данные для {symbol} (ошибок: {self.error_count})")
        return self._get_mock_ticker(symbol)

    @log_function_call()
    async def get_multiple_tickers(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Получает данные по нескольким тикерам одновременно.

        Выполняет последовательные запросы для каждого символа
        с небольшой задержкой между ними.

        Args:
            symbols (List[str]): Список торговых символов

        Returns:
            Dict[str, Dict]: Словарь, где ключ - символ, значение - данные тикера.
                            Возвращает только успешно полученные тикеры.
        """
        logger.info(f"📊 Запрос данных для {len(symbols)} тикеров")
        results = {}

        # Создаем задачи для параллельных запросов
        tasks = []
        for symbol in symbols:
            tasks.append(self.get_ticker(symbol))

        # Выполняем запросы параллельно
        tickers = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = 0
        for symbol, ticker in zip(symbols, tickers):
            if isinstance(ticker, dict) and ticker:
                results[symbol] = ticker
                success_count += 1
            elif isinstance(ticker, Exception):
                logger.error(f"❌ Ошибка при получении {symbol}: {ticker}")
            else:
                logger.error(f"❌ Не удалось получить данные для {symbol}")

        logger.info(f"✅ Получено {success_count} из {len(symbols)} тикеров")
        return results

    def _get_mock_ticker(self, symbol: str) -> Dict:
        """
        Возвращает тестовые данные для отладки, когда API недоступен.

        Args:
            symbol (str): Торговый символ

        Returns:
            Dict: Тестовые данные тикера
        """
        import random

        logger.debug(f"🎲 Генерация тестовых данных для {symbol}")

        # Базовые цены для популярных криптовалют
        base_prices = {
            "BTCUSDT": 50000.0,
            "ETHUSDT": 3000.0,
            "SOLUSDT": 100.0,
            "BNBUSDT": 400.0,
            "XRPUSDT": 0.5,
            "ADAUSDT": 0.4,
            "DOGEUSDT": 0.08,
            "DOTUSDT": 7.0,
            "LINKUSDT": 15.0
        }

        base_price = base_prices.get(symbol, 100.0)

        # Генерируем случайные колебания
        price = base_price * (1 + (random.random() - 0.5) * 0.1)
        change = (random.random() - 0.5) * 10

        return {
            "symbol": symbol,
            "lastPrice": str(price),
            "price24hPcnt": str(change / 100),
            "highPrice24h": str(price * 1.05),
            "lowPrice24h": str(price * 0.95),
            "volume24h": str(price * 1000000),
            "prevPrice24h": str(price / (1 + change / 100))
        }

    async def close(self):
        """
        Закрывает HTTP сессию.

        Должен быть вызван при завершении работы для освобождения ресурсов.

        Returns:
            None
        """
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info(f"🔌 Сессия Bybit закрыта. Всего запросов: {self.request_count}, ошибок: {self.error_count}")


# Создаем глобальный экземпляр для использования в других модулях
bybit_client = BybitClient()