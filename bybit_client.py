import aiohttp
import asyncio
from typing import Dict, List, Optional


class BybitClient:
    def __init__(self):
        self.session = None
        self.base_url = "https://api.bybit.com"

    async def get_ticker(self, symbol: str) -> Optional[Dict]:
        """Получить данные по тикеру"""
        try:
            url = f"{self.base_url}/v5/market/tickers"
            params = {"category": "spot", "symbol": symbol}

            if not self.session:
                self.session = aiohttp.ClientSession()

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data["retCode"] == 0 and data["result"]["list"]:
                        return data["result"]["list"][0]
        except Exception as e:
            print(f"Ошибка при получении тикера {symbol}: {e}")
        return None

    async def get_multiple_tickers(self, symbols: List[str]) -> Dict[str, Dict]:
        """Получить цены для нескольких символов"""
        results = {}
        for symbol in symbols:
            ticker = await self.get_ticker(symbol)
            if ticker:
                results[symbol] = ticker
            await asyncio.sleep(0.1)
        return results

    async def close(self):
        """Закрыть сессию"""
        if self.session:
            await self.session.close()