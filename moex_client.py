import aiohttp
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
import json

from config import Config
from logger import get_logger
from utils import to_decimal

logger = get_logger('moex_client')


class MOEXClient:
    """Клиент для работы с API Московской биржи"""

    ENGINE_MARKET_MAP = {
        'stock': ('stock', 'shares'),
        'bond': ('stock', 'bonds'),
        'etf': ('stock', 'etf'),
        'currency': ('currency', 'selt'),
        'futures': ('futures', 'forts'),
        'index': ('stock', 'index'),
    }

    def __init__(self):
        self.base_url = Config.MOEX_API_URL
        self.session: Optional[aiohttp.ClientSession] = None
        self.cache = {}
        self.info_cache = {}
        self.cache_ttl = Config.PRICE_CACHE_TTL
        self._lock = asyncio.Lock()
        self.last_known_prices = {}

        self.request_count = 0
        self.last_request_reset = datetime.now()
        self.max_requests_per_minute = Config.MOEX_RATE_LIMIT_PER_MIN

    async def _get_session(self) -> aiohttp.ClientSession:
        """Получение или создание HTTP сессии"""
        async with self._lock:
            if self.session is None or self.session.closed:
                timeout = aiohttp.ClientTimeout(
                    total=Config.MOEX_REQUEST_TIMEOUT,
                    connect=Config.MOEX_CONNECT_TIMEOUT,
                    sock_read=Config.MOEX_REQUEST_TIMEOUT - 5
                )
                connector = aiohttp.TCPConnector(
                    ssl=False,
                    limit=10,
                    ttl_dns_cache=300,
                    force_close=True
                )
                self.session = aiohttp.ClientSession(
                    timeout=timeout,
                    connector=connector,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Accept': 'application/json',
                        'Accept-Encoding': 'gzip, deflate',
                        'Connection': 'keep-alive'
                    }
                )
                logger.info("✅ Создана новая HTTP сессия для MOEX")
        return self.session

    async def _check_rate_limit(self):
        """Проверка и соблюдение лимитов запросов"""
        now = datetime.now()
        if (now - self.last_request_reset).total_seconds() > 60:
            self.request_count = 0
            self.last_request_reset = now

        self.request_count += 1

        if self.request_count > self.max_requests_per_minute:
            wait_time = 60 - (now - self.last_request_reset).total_seconds()
            if wait_time > 0:
                logger.warning(f"⚠️ Достигнут лимит запросов, ожидание {wait_time:.1f}с")
                await asyncio.sleep(wait_time)
                self.request_count = 0
                self.last_request_reset = datetime.now()

    async def _make_request(self, url: str, params: Dict = None) -> Optional[Dict]:
        """Выполнение запроса к API MOEX с повторными попытками"""
        max_retries = Config.MOEX_MAX_RETRIES
        retry_delay = Config.MOEX_RETRY_DELAY

        await self._check_rate_limit()

        logger.info(f"🌐 ЗАПРОС К MOEX: {url}")
        if params:
            logger.info(f"📦 Параметры: {params}")

        for attempt in range(max_retries):
            try:
                session = await self._get_session()

                if params is None:
                    params = {}

                if 'iss.only' not in params:
                    params['iss.only'] = 'securities,marketdata'

                params['iss.meta'] = 'off'
                params['lang'] = 'ru'

                start_time = datetime.now()
                async with session.get(url, params=params) as response:
                    elapsed = (datetime.now() - start_time).total_seconds()

                    logger.info(f"⏱️ Время ответа: {elapsed:.2f}с, Статус: {response.status}")

                    actual_url = str(response.url)
                    logger.info(f"🔗 Фактический URL: {actual_url}")

                    if response.status == 200:
                        data = await response.json()

                        if 'securities' in data:
                            securities_data = data['securities']
                            if 'data' in securities_data:
                                boards = set()
                                for row in securities_data['data']:
                                    if len(row) > 1:
                                        boards.add(row[1])
                                logger.info(f"📊 Найденные режимы (BOARDID): {boards}")

                        if 'marketdata' in data:
                            marketdata = data['marketdata']
                            if 'data' in marketdata:
                                logger.info(f"📈 marketdata строк: {len(marketdata['data'])}")

                        logger.info(f"✅ Успешный ответ, размер: {len(str(data))} байт")
                        return data
                    elif response.status == 404:
                        logger.warning(f"❌ 404 Not Found: {url}")
                        return None
                    elif response.status == 429:
                        wait_time = retry_delay * (attempt + 3)
                        logger.warning(f"⚠️ 429 Too Many Requests, ждем {wait_time}с")
                        await asyncio.sleep(wait_time)
                    elif response.status >= 500:
                        wait_time = retry_delay * (attempt + 2)
                        logger.warning(f"⚠️ {response.status} Server Error, ждем {wait_time}с")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"❌ Ошибка {response.status}: {url}")
                        return None

            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Таймаут запроса (попытка {attempt + 1}/{max_retries})")
            except aiohttp.ClientConnectorError as e:
                logger.warning(f"🔌 Ошибка подключения (попытка {attempt + 1}/{max_retries}): {e}")
            except Exception as e:
                logger.error(f"💥 Неизвестная ошибка: {e}", exc_info=True)

            if attempt < max_retries - 1:
                wait_time = retry_delay * (attempt + 1)
                logger.info(f"⏳ Повторная попытка через {wait_time}с...")
                await asyncio.sleep(wait_time)

        logger.error(f"❌ Не удалось выполнить запрос после {max_retries} попыток: {url}")
        return None

    def _determine_engine_market(self, symbol: str, asset_type_hint: str = None) -> Tuple[str, str]:
        """Определение engine и market для символа на основе общих правил"""
        symbol = symbol.upper()
        logger.debug(f"🔍 Определение engine/market для {symbol}, подсказка: {asset_type_hint}")

        if asset_type_hint and asset_type_hint in self.ENGINE_MARKET_MAP:
            result = self.ENGINE_MARKET_MAP[asset_type_hint]
            logger.debug(f"✅ Используем подсказку: {result}")
            return result

        if symbol.endswith('F') and len(symbol) == 4 and symbol[0].isalpha():
            logger.debug(f"✅ Похоже на фьючерс")
            return 'futures', 'forts'

        if symbol.endswith('T') and len(symbol) == 4 and symbol[0].isalpha():
            return 'futures', 'forts'

        if len(symbol) <= 4 and symbol.isalpha():
            logger.debug(f"✅ Короткий буквенный тикер, скорее всего акция")
            return 'stock', 'shares'

        logger.debug(f"✅ Используем по умолчанию: акции")
        return 'stock', 'shares'

    async def get_security_info(self, symbol: str, asset_type_hint: str = None) -> Optional[Dict]:
        """Получение детальной информации об инструменте"""
        symbol = symbol.upper().strip()
        logger.info(f"🔍 ПОИСК ИНФОРМАЦИИ: {symbol} (подсказка: {asset_type_hint})")

        cache_key = f"info_{symbol}"

        if cache_key in self.info_cache:
            data, timestamp = self.info_cache[cache_key]
            if datetime.now() - timestamp < timedelta(seconds=self.cache_ttl * 2):
                logger.info(f"📦 Данные из кэша для {symbol}")
                return data

        engine, market = self._determine_engine_market(symbol, asset_type_hint)

        url = f"{self.base_url}/engines/{engine}/markets/{market}/securities/{symbol}.json"
        logger.info(f"🔗 Пробуем URL: {url}")

        params = {
            'iss.meta': 'off',
            'iss.only': 'securities,marketdata',
            'lang': 'ru',
            'marketdata.columns': 'SECID,BOARDID,LAST,LCURRENTPRICE,MARKETPRICE,CLOSEPRICE,PREVPRICE,WAPRICE,OPEN,HIGH,LOW'
        }

        response = await self._make_request(url, params)

        if not response:
            logger.warning(f"❌ Не найдено на {engine}/{market}, пробуем альтернативы...")

            alt_options = [
                ('stock', 'shares'),
                ('stock', 'bonds'),
                ('stock', 'etf'),
                ('currency', 'selt'),
                ('futures', 'forts'),
                ('stock', 'index'),
            ]

            for alt_engine, alt_market in alt_options:
                if (alt_engine, alt_market) == (engine, market):
                    continue

                alt_url = f"{self.base_url}/engines/{alt_engine}/markets/{alt_market}/securities/{symbol}.json"
                logger.info(f"🔄 Пробуем альтернативу: {alt_url}")

                response = await self._make_request(alt_url, params)
                if response:
                    engine, market = alt_engine, alt_market
                    logger.info(f"✅ Найдено на {engine}/{market}")
                    break

        if not response:
            logger.warning(f"❌ Инструмент {symbol} не найден нигде")
            return None

        logger.info(f"📝 Парсинг ответа для {symbol}...")
        result = await self._parse_security_response(symbol, response, engine, market)

        if result:
            self.info_cache[cache_key] = (result, datetime.now())
            logger.info(f"✅ Успешно получена информация для {symbol}: {result.get('name')}")
            logger.info(f"   Тип: {result.get('asset_type')}, Валюта: {result.get('currency')}")
            if result.get('current_price'):
                logger.info(f"   Цена: {result.get('current_price')}")
            else:
                logger.warning(f"⚠️ Цена для {symbol} не найдена в ответе")
        else:
            logger.warning(f"❌ Не удалось распарсить ответ для {symbol}")

        return result

    async def _parse_security_response(self, symbol: str, response: Dict, engine: str, market: str) -> Optional[Dict]:
        """Парсинг ответа от MOEX"""
        try:
            result = {
                'symbol': symbol.upper(),
                'name': symbol,
                'asset_type': self._map_engine_market_to_type(engine, market),
                'currency': 'RUB',  # По умолчанию RUB
                'lot_size': 1,
                'engine': engine,
                'market': market,
                'market_data': {},
                'description': {},
                'found': False,
                'current_price': None
            }

            logger.debug(f"Блоки в ответе для {symbol}: {list(response.keys())}")

            for block_name, block_data in response.items():
                if not isinstance(block_data, dict) or 'data' not in block_data:
                    continue

                columns = block_data.get('columns', [])
                rows = block_data.get('data', [])

                if not columns or not rows:
                    continue

                if block_name == 'description':
                    for row in rows:
                        if isinstance(row, list) and len(row) >= 2:
                            key = row[0]
                            value = row[1] if len(row) > 1 else None
                            if key and value is not None:
                                result['description'][key] = value
                                result['found'] = True

                elif block_name == 'securities':
                    for row in rows:
                        if not isinstance(row, list):
                            continue

                        row_dict = dict(zip(columns, row))

                        if row_dict.get('SHORTNAME'):
                            result['name'] = str(row_dict['SHORTNAME'])
                        elif row_dict.get('SECNAME'):
                            result['name'] = str(row_dict['SECNAME'])

                        if row_dict.get('CURRENCYID'):
                            currency = str(row_dict['CURRENCYID'])
                            if currency in ['SUR', 'RUR']:
                                currency = 'RUB'
                            result['currency'] = currency

                        if row_dict.get('LOTSIZE'):
                            try:
                                result['lot_size'] = int(row_dict['LOTSIZE'])
                            except (ValueError, TypeError):
                                pass

                        if row_dict.get('SECTOR'):
                            result['sector'] = str(row_dict['SECTOR'])

                        result['found'] = True

                elif block_name == 'marketdata':
                    priority_boards = ['TQBR', 'TQTF', 'TQBD', 'CETS', 'FUT']

                    for priority_board in priority_boards:
                        for row in rows:
                            if not isinstance(row, list):
                                continue

                            row_dict = dict(zip(columns, row))
                            board_id = row_dict.get('BOARDID', '')

                            if board_id == priority_board:
                                for key, value in row_dict.items():
                                    if value is not None:
                                        result['market_data'][key] = value

                                price = self._extract_price_from_row(row_dict)
                                if price:
                                    result['current_price'] = price
                                    result['found'] = True
                                    logger.debug(f"💰 Цена найдена в режиме {board_id}: {price}")
                                    break

                        if result.get('current_price'):
                            break

                    if not result.get('current_price'):
                        for row in rows:
                            if not isinstance(row, list):
                                continue

                            row_dict = dict(zip(columns, row))
                            price = self._extract_price_from_row(row_dict)

                            if price:
                                result['current_price'] = price
                                result['found'] = True
                                board_id = row_dict.get('BOARDID', 'unknown')
                                logger.debug(f"💰 Цена найдена в режиме {board_id}: {price}")
                                break

            if not result.get('current_price') and 'securities' in response:
                securities_data = response['securities']
                columns = securities_data.get('columns', [])
                rows = securities_data.get('data', [])

                for row in rows:
                    if not isinstance(row, list):
                        continue

                    row_dict = dict(zip(columns, row))
                    if row_dict.get('PREVPRICE'):
                        price = to_decimal(row_dict['PREVPRICE'])
                        if price and price > 0:
                            result['current_price'] = price
                            result['found'] = True
                            logger.debug(f"💰 Используем PREVPRICE как запасной вариант: {price}")
                            break

            if result.get('current_price'):
                logger.info(f"✅ Успешно получена цена для {symbol}: {result['current_price']} {result['currency']}")
            else:
                logger.warning(f"⚠️ Цена для {symbol} не найдена")

            return result if result.get('found') else None

        except Exception as e:
            logger.error(f"Ошибка парсинга ответа для {symbol}: {e}", exc_info=True)
            return None

    def _extract_price_from_row(self, row_dict: Dict) -> Optional[Decimal]:
        """Извлечение цены из строки marketdata (общий метод)"""

        price_fields = [
            'LCURRENTPRICE',  # Текущая цена
            'LAST',  # Последняя сделка
            'MARKETPRICE',  # Рыночная цена
            'CLOSEPRICE',  # Цена закрытия
            'PREVPRICE',  # Цена предыдущего закрытия
            'WAPRICE',  # Средневзвешенная цена
            'OPEN',  # Цена открытия
            'HIGH',  # Максимум
            'LOW'  # Минимум
        ]

        for field in price_fields:
            if field in row_dict and row_dict[field] is not None:
                price = to_decimal(row_dict[field])
                if price and price > 0:
                    return price

        return None

    def _map_engine_market_to_type(self, engine: str, market: str) -> str:
        """Преобразование engine/market в тип актива"""
        if engine == 'stock':
            if market == 'shares':
                return 'stock'
            elif market == 'bonds':
                return 'bond'
            elif market == 'etf':
                return 'etf'
            elif market == 'index':
                return 'index'
        elif engine == 'currency':
            return 'currency'
        elif engine == 'futures':
            return 'futures'
        return 'stock'

    async def get_current_price(self, symbol: str, asset_type_hint: str = None) -> Optional[Decimal]:
        """Получение текущей цены инструмента"""
        logger.info(f"💰 ЗАПРОС ЦЕНЫ: {symbol}")

        symbol = symbol.upper().strip()
        cache_key = f"price_{symbol}"

        if cache_key in self.cache:
            price, timestamp = self.cache[cache_key]
            if datetime.now() - timestamp < timedelta(seconds=self.cache_ttl):
                logger.info(f"📦 Цена из кэша для {symbol}: {price}")
                return price

        info = await self.get_security_info(symbol, asset_type_hint)
        if not info:
            logger.warning(f"❌ Не удалось получить информацию для {symbol}")
            return None

        price = info.get('current_price')

        if price and price > 0:
            self.cache[cache_key] = (price, datetime.now())
            self.last_known_prices[symbol] = price
            logger.info(f"✅ Получена цена {symbol}: {price}")
            return price

        logger.warning(f"⚠️ Не удалось получить цену {symbol}")
        return None

    async def get_prices(self, symbols: List[str], asset_types: Dict[str, str] = None) -> Dict[str, Decimal]:
        """
        Получение цен нескольких символов одновременно

        Args:
            symbols: Список символов
            asset_types: Словарь с типами активов для каждого символа (опционально)

        Returns:
            Dict[str, Decimal]: Словарь {символ: цена}
        """
        logger.info(f"💰 ПОЛУЧЕНИЕ ЦЕН ДЛЯ {len(symbols)} СИМВОЛОВ")

        result = {}

        tasks = []
        for symbol in symbols:
            asset_type = None
            if asset_types and symbol in asset_types:
                asset_type = asset_types[symbol]

            tasks.append(self.get_current_price(symbol, asset_type))

        prices = await asyncio.gather(*tasks, return_exceptions=True)

        for i, symbol in enumerate(symbols):
            price = prices[i]
            if isinstance(price, Exception):
                logger.error(f"Ошибка получения цены для {symbol}: {price}")
            elif price is not None:
                result[symbol] = price
                logger.debug(f"✅ {symbol}: {price}")

        logger.info(f"✅ Получены цены для {len(result)}/{len(symbols)} символов")
        return result

    async def validate_symbol(self, symbol: str, asset_type_hint: str = None) -> Tuple[bool, Optional[Dict]]:
        """Проверка существования символа"""
        logger.info(f"✅ ПРОВЕРКА СИМВОЛА: {symbol}")
        info = await self.get_security_info(symbol, asset_type_hint)
        if info and info.get('found'):
            return True, info
        return False, None

    async def close(self):
        """Закрытие сессии"""
        async with self._lock:
            if self.session and not self.session.closed:
                try:
                    await self.session.close()
                    logger.info("✅ Сессия MOEX закрыта")
                except Exception as e:
                    logger.error(f"Ошибка при закрытии сессии: {e}")
                finally:
                    self.session = None


moex_client = MOEXClient()