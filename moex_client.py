import aiohttp
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

from config import Config
from logger import get_logger
from utils import to_decimal

logger = get_logger('moex_client')


class MOEXClient:
    """Клиент для работы с API Московской биржи"""

    def __init__(self):
        self.base_url = Config.MOEX_API_URL
        self.session: Optional[aiohttp.ClientSession] = None
        self.cache = {}  # Кэш для запросов
        self.cache_ttl = Config.PRICE_CACHE_TTL
        self._lock = asyncio.Lock()  # Блокировка для безопасного создания сессии

    async def _get_session(self) -> aiohttp.ClientSession:
        """Получение HTTP сессии с блокировкой"""
        async with self._lock:
            if self.session is None or self.session.closed:
                # Создаем сессию с таймаутами
                timeout = aiohttp.ClientTimeout(
                    total=Config.MOEX_REQUEST_TIMEOUT,
                    connect=5,
                    sock_read=Config.MOEX_REQUEST_TIMEOUT
                )
                connector = aiohttp.TCPConnector(ssl=False)  # Отключаем SSL для ускорения
                self.session = aiohttp.ClientSession(
                    timeout=timeout,
                    connector=connector
                )
                logger.debug("Создана новая HTTP сессия для MOEX")
        return self.session

    async def _make_request(self, url: str, params: Dict = None) -> Optional[Dict]:
        """Выполнение запроса к API MOEX"""
        try:
            session = await self._get_session()

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    if 'json' in url or params and params.get('format') == 'json':
                        return await response.json()
                    else:
                        # Для XML ответов
                        text = await response.text()
                        return self._parse_xml(text)
                else:
                    logger.error(f"Ошибка MOEX API: {response.status} - {await response.text()}")
                    return None

        except asyncio.TimeoutError:
            logger.error(f"Таймаут запроса к MOEX: {url}")
            return None
        except aiohttp.ClientConnectorError as e:
            logger.error(f"Ошибка подключения к MOEX: {e}")
            return None
        except Exception as e:
            logger.error(f"Ошибка запроса к MOEX: {e}")
            return None

    def _parse_xml(self, xml_text: str) -> Dict:
        """Парсинг XML ответа от MOEX"""
        try:
            root = ET.fromstring(xml_text)
            result = {}

            for data in root.findall('.//data'):
                data_id = data.get('id')
                rows = []

                for row in data.findall('.//rows/row'):
                    row_data = {}
                    for key, value in row.attrib.items():
                        row_data[key] = value
                    rows.append(row_data)

                result[data_id] = rows

            return result
        except Exception as e:
            logger.error(f"Ошибка парсинга XML: {e}")
            return {}

    async def search_securities(self, query: str, limit: int = 10) -> List[Dict]:
        """Поиск инструментов на MOEX"""
        cache_key = f"search_{query}"

        # Проверка кэша
        if cache_key in self.cache:
            data, timestamp = self.cache[cache_key]
            if datetime.now() - timestamp < timedelta(seconds=self.cache_ttl):
                return data

        url = f"{self.base_url}/securities.json"
        params = {
            'q': query,
            'lang': 'ru',
            'limit': limit
        }

        response = await self._make_request(url, params)
        result = []

        if response and 'securities' in response:
            securities = response['securities'].get('data', [])
            columns = response['securities'].get('columns', [])

            for row in securities[:limit]:
                security = dict(zip(columns, row))

                # Определяем тип инструмента
                asset_type = self._determine_asset_type(security)

                result.append({
                    'symbol': security.get('SECID'),
                    'name': security.get('SHORTNAME') or security.get('SECNAME'),
                    'full_name': security.get('LATNAME') or security.get('SECNAME'),
                    'asset_type': asset_type,
                    'currency': security.get('CURRENCYID', 'RUB'),
                    'market': security.get('MARKET'),
                    'engine': security.get('ENGINE'),
                    'isin': security.get('ISIN'),
                    'lot_size': int(security.get('LOTSIZE', 1))
                })

        # Сохраняем в кэш
        self.cache[cache_key] = (result, datetime.now())
        return result

    async def get_security_info(self, symbol: str) -> Optional[Dict]:
        """Получение детальной информации об инструменте"""
        cache_key = f"info_{symbol}"

        if cache_key in self.cache:
            data, timestamp = self.cache[cache_key]
            if datetime.now() - timestamp < timedelta(seconds=self.cache_ttl * 2):
                return data

        # Сначала ищем по символу
        url = f"{self.base_url}/securities/{symbol}.json"
        response = await self._make_request(url)

        if not response:
            return None

        result = {
            'symbol': symbol,
            'description': {},
            'prices': {},
            'market_data': {}
        }

        # Парсим описание
        if 'description' in response:
            desc_data = response['description'].get('data', [])
            desc_cols = response['description'].get('columns', [])
            for row in desc_data:
                result['description'] = dict(zip(desc_cols, row))

        # Парсим рыночные данные
        if 'marketdata' in response:
            market_data = response['marketdata'].get('data', [])
            market_cols = response['marketdata'].get('columns', [])
            for row in market_data:
                result['market_data'] = dict(zip(market_cols, row))

        # Определяем тип и рынок
        if result['description']:
            # Безопасное получение имени
            name = result['description'].get('SHORTNAME')
            if name is None:
                name = result['description'].get('SECNAME', symbol)

            result['asset_type'] = self._determine_asset_type(result['description'])
            result['currency'] = result['description'].get('CURRENCYID', 'RUB')
            result['name'] = name
            result['lot_size'] = int(result['description'].get('LOTSIZE', 1))
            return result
        else:
            # Если нет описания, но символ существует (например, валютная пара)
            result['asset_type'] = 'other'
            result['currency'] = 'RUB'
            result['name'] = symbol
            result['lot_size'] = 1
            return result

        self.cache[cache_key] = (result, datetime.now())
        return result

    async def get_current_price(self, symbol: str) -> Optional[Decimal]:
        """Получение текущей цены инструмента"""
        cache_key = f"price_{symbol}"

        # Проверка кэша
        if cache_key in self.cache:
            price, timestamp = self.cache[cache_key]
            if datetime.now() - timestamp < timedelta(seconds=self.cache_ttl):
                return price

        # Получаем информацию
        info = await self.get_security_info(symbol)
        if not info:
            return None

        price = None
        market_data = info.get('market_data', {})

        # Пробуем разные поля с ценами
        if market_data.get('LAST'):
            price = to_decimal(market_data['LAST'])
        elif market_data.get('CURRENTVALUE'):
            price = to_decimal(market_data['CURRENTVALUE'])
        elif market_data.get('LCURRENTPRICE'):
            price = to_decimal(market_data['LCURRENTPRICE'])

        if price:
            # Сохраняем в кэш
            self.cache[cache_key] = (price, datetime.now())
            return price

        return None

    async def get_prices(self, symbols: List[str]) -> Dict[str, Decimal]:
        """Получение цен нескольких инструментов"""
        result = {}
        tasks = []

        for symbol in symbols:
            tasks.append(self.get_current_price(symbol))

        prices = await asyncio.gather(*tasks, return_exceptions=True)

        for symbol, price in zip(symbols, prices):
            if isinstance(price, Decimal) and price > 0:
                result[symbol] = price

        return result

    async def get_market_trading_status(self, symbol: str) -> Dict[str, Any]:
        """Получение статуса торгов по инструменту"""
        info = await self.get_security_info(symbol)
        if not info:
            return {'is_trading': False, 'status': 'unknown'}

        market_data = info.get('market_data', {})
        status = market_data.get('TRADINGSTATUS', 'unknown')

        # Определяем, идут ли торги
        is_trading = status in ['T', 'Normal', 'Open']

        return {
            'is_trading': is_trading,
            'status': status,
            'last_price': to_decimal(market_data.get('LAST')),
            'change': to_decimal(market_data.get('LASTCHANGE')),
            'change_percent': to_decimal(market_data.get('LASTCHANGEPRCNT')),
            'volume': market_data.get('VOLTODAY'),
            'time': market_data.get('TIME')
        }

    async def get_board_info(self, symbol: str) -> Optional[Dict]:
        """Получение информации о режиме торгов"""
        url = f"{self.base_url}/securities/{symbol}/boards.json"
        response = await self._make_request(url)

        if response and 'boards' in response:
            boards_data = response['boards'].get('data', [])
            boards_cols = response['boards'].get('columns', [])

            for row in boards_data:
                board = dict(zip(boards_cols, row))
                if board.get('is_primary', False) or board.get('boardid') == 'TQBR':
                    return {
                        'board_id': board.get('boardid'),
                        'engine': board.get('engine'),
                        'market': board.get('market'),
                        'title': board.get('title'),
                        'is_traded': board.get('is_traded', False)
                    }

        return None

    def _determine_asset_type(self, security: Dict) -> str:
        """Определение типа актива по данным MOEX"""
        # Пробуем определить по типу инструмента
        sec_type = security.get('TYPENAME', '').upper()
        group = security.get('GROUP', '').upper()

        if 'АКЦИЯ' in sec_type or 'SHARE' in sec_type:
            return 'stock'
        elif 'ОБЛИГАЦИЯ' in sec_type or 'BOND' in sec_type:
            return 'bond'
        elif 'ETF' in sec_type or 'ПИФ' in sec_type or 'ETFS' in group:
            return 'etf'
        elif 'ВАЛЮТА' in sec_type or 'CURRENCY' in sec_type:
            return 'currency'
        elif 'ФЬЮЧЕРС' in sec_type or 'FUTURES' in sec_type:
            return 'futures'
        else:
            return 'other'

    async def get_historical_prices(self, symbol: str, days: int = 30) -> List[Dict]:
        """Получение исторических цен"""
        from datetime import date, timedelta

        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        url = f"{self.base_url}/history/engines/stock/markets/shares/securities/{symbol}.json"
        params = {
            'from': start_date.strftime('%Y-%m-%d'),
            'till': end_date.strftime('%Y-%m-%d'),
            'limit': days
        }

        response = await self._make_request(url, params)
        result = []

        if response and 'history' in response:
            history_data = response['history'].get('data', [])
            history_cols = response['history'].get('columns', [])

            for row in history_data:
                item = dict(zip(history_cols, row))
                result.append({
                    'date': item.get('TRADEDATE'),
                    'open': to_decimal(item.get('OPEN')),
                    'high': to_decimal(item.get('HIGH')),
                    'low': to_decimal(item.get('LOW')),
                    'close': to_decimal(item.get('CLOSE')),
                    'volume': item.get('VOLUME')
                })

        return result

    async def get_index_composition(self, index: str = 'IMOEX') -> List[Dict]:
        """Получение состава индекса (IMOEX, RTSI и т.д.)"""
        url = f"{self.base_url}/statistics/engines/stock/markets/index/analytics/{index}.json"
        response = await self._make_request(url)

        result = []
        if response and 'analytics' in response:
            analytics_data = response['analytics'].get('data', [])
            analytics_cols = response['analytics'].get('columns', [])

            for row in analytics_data:
                item = dict(zip(analytics_cols, row))
                result.append({
                    'symbol': item.get('SECID'),
                    'name': item.get('SECNAME'),
                    'weight': float(item.get('WEIGHT', 0)) / 100,
                    'price': to_decimal(item.get('PRICE'))
                })

        return result

    async def close(self):
        """Закрытие сессии с таймаутом"""
        async with self._lock:
            if self.session and not self.session.closed:
                logger.info("🔄 Закрытие сессии MOEX...")
                try:
                    # Даем время на завершение текущих запросов
                    await asyncio.sleep(0.5)
                    await self.session.close()
                    logger.info("✅ Сессия MOEX закрыта")
                except Exception as e:
                    logger.error(f"Ошибка при закрытии сессии MOEX: {e}")
                finally:
                    self.session = None

    def clear_cache(self):
        """Очистка кэша"""
        self.cache.clear()
        logger.info("🧹 Кэш MOEX очищен")


# Глобальный экземпляр клиента MOEX
moex_client = MOEXClient()