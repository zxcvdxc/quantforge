"""
A股数据源 - Tushare接口
Tushare API文档: https://tushare.pro/document/2
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Dict, Any
import aiohttp
import asyncio

from ..base import BaseDataSource
from ..types import KlineData, TickData, SymbolInfo, Exchange, MarketType
from ..exceptions import DataSourceError, ConnectionError


class TushareClient(BaseDataSource):
    """Tushare A股数据源客户端"""
    
    API_BASE_URL = "https://api.tushare.pro"
    
    # K线周期映射
    INTERVAL_MAP = {
        "1m": "1",
        "5m": "5",
        "15m": "15",
        "30m": "30",
        "60m": "60",
        "1d": "D",
        "1w": "W",
        "1M": "M",
    }
    
    # 交易所代码映射
    EXCHANGE_MAP = {
        "SH": Exchange.SSE,
        "SZ": Exchange.SZSE,
        "BJ": Exchange.BSE,
    }
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("Tushare", config)
        self.token = self.config.get("token")
        if not self.token:
            raise DataSourceError("Tushare token is required", source="Tushare")
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def connect(self) -> None:
        """建立连接"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        self._connected = True
    
    async def disconnect(self) -> None:
        """断开连接"""
        if self.session:
            await self.session.close()
            self.session = None
        self._connected = False
    
    async def _request(self, api_name: str, params: Optional[Dict] = None) -> Dict:
        """发送API请求"""
        if not self.session:
            await self.connect()
        
        payload = {
            "api_name": api_name,
            "token": self.token,
            "params": params or {},
            "fields": "",
        }
        
        try:
            async with self.session.post(
                self.API_BASE_URL,
                json=payload
            ) as response:
                response.raise_for_status()
                result = await response.json()
                
                if result.get("code") != 0:
                    raise DataSourceError(
                        f"Tushare API error: {result.get('msg')}",
                        source="Tushare"
                    )
                return result
        except aiohttp.ClientError as e:
            raise ConnectionError(f"Tushare connection error: {e}")
    
    def _get_exchange(self, ts_code: str) -> Exchange:
        """从股票代码获取交易所"""
        suffix = ts_code.split(".")[-1] if "." in ts_code else ""
        return self.EXCHANGE_MAP.get(suffix, Exchange.SSE)
    
    async def get_kline(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[KlineData]:
        """获取K线数据
        
        Args:
            symbol: 股票代码，如 "000001.SZ"
            interval: K线周期
            start_time: 开始时间
            end_time: 结束时间
            limit: 返回条数限制
        """
        ts_interval = self.INTERVAL_MAP.get(interval, "D")
        
        params = {
            "ts_code": symbol,
            "freq": ts_interval,
        }
        
        if start_time:
            params["start_date"] = start_time.strftime("%Y%m%d")
        if end_time:
            params["end_date"] = end_time.strftime("%Y%m%d")
        
        # 分钟线使用不同的API
        if interval in ["1m", "5m", "15m", "30m", "60m"]:
            result = await self._request("stk_mins", params=params)
        else:
            result = await self._request("daily", params=params)
        
        fields = result.get("data", {}).get("fields", [])
        items = result.get("data", {}).get("items", [])
        
        # 找到字段索引
        field_map = {f: i for i, f in enumerate(fields)}
        
        klines = []
        for item in items:
            # 根据字段名获取数据
            trade_time_str = item[field_map.get("trade_time", field_map.get("trade_date", 0))]
            
            # 解析时间
            if len(trade_time_str) == 14:  # 分钟线格式: YYYYMMDDHHMMSS
                ts = datetime.strptime(trade_time_str, "%Y%m%d%H%M%S")
            else:  # 日线格式: YYYYMMDD
                ts = datetime.strptime(trade_time_str, "%Y%m%d")
            
            klines.append(KlineData(
                timestamp=ts.replace(tzinfo=timezone.utc),
                open=Decimal(str(item[field_map.get("open", 1)])),
                high=Decimal(str(item[field_map.get("high", 2)])),
                low=Decimal(str(item[field_map.get("low", 3)])),
                close=Decimal(str(item[field_map.get("close", 4)])),
                volume=Decimal(str(item[field_map.get("vol", field_map.get("volume", 5))])),
                quote_volume=Decimal(str(item[field_map.get("amount", 6)])) if "amount" in field_map else None,
            ))
        
        return sorted(klines, key=lambda x: x.timestamp)[-limit:]
    
    async def get_tick(self, symbol: str, limit: int = 100) -> List[TickData]:
        """获取Tick数据（Tushare需要付费权限，这里返回模拟数据）"""
        # Tushare的逐笔成交数据需要高权限
        # 这里使用实时行情数据模拟
        params = {
            "ts_code": symbol,
        }
        result = await self._request("snapshot", params=params)
        
        ticks = []
        fields = result.get("data", {}).get("fields", [])
        items = result.get("data", {}).get("items", [])
        
        if items:
            item = items[0]
            field_map = {f: i for i, f in enumerate(fields)}
            
            ticks.append(TickData(
                timestamp=datetime.now(timezone.utc),
                symbol=symbol,
                price=Decimal(str(item[field_map.get("last_price", 0)])),
                volume=Decimal("0"),
            ))
        
        return ticks
    
    async def get_symbols(self, market_type: Optional[MarketType] = None) -> List[SymbolInfo]:
        """获取股票列表"""
        result = await self._request("stock_basic", params={
            "exchange": "",
            "list_status": "L",  # 上市
        })
        
        symbols = []
        fields = result.get("data", {}).get("fields", [])
        items = result.get("data", {}).get("items", [])
        field_map = {f: i for i, f in enumerate(fields)}
        
        for item in items:
            ts_code = item[field_map.get("ts_code", 0)]
            exchange = item[field_map.get("exchange", 2)]
            
            symbols.append(SymbolInfo(
                symbol=ts_code,
                exchange=self.EXCHANGE_MAP.get(exchange, Exchange.SSE),
                market_type=MarketType.STOCK,
                name=item[field_map.get("name", 1)],
            ))
        
        return symbols
    
    async def get_daily_basic(self, symbol: str, trade_date: Optional[str] = None) -> Dict[str, Any]:
        """获取每日基本面数据"""
        params = {"ts_code": symbol}
        if trade_date:
            params["trade_date"] = trade_date
        
        result = await self._request("daily_basic", params=params)
        fields = result.get("data", {}).get("fields", [])
        items = result.get("data", {}).get("items", [])
        
        if items:
            return dict(zip(fields, items[0]))
        return {}


class AKShareClient(BaseDataSource):
    """AKShare A股数据源客户端 - 同步接口包装为异步"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("AKShare", config)
        self._loop = None
        try:
            import akshare as ak
            self.ak = ak
        except ImportError:
            raise DataSourceError(
                "AKShare not installed. Run: pip install akshare",
                source="AKShare"
            )
    
    async def connect(self) -> None:
        """建立连接"""
        self._connected = True
    
    async def disconnect(self) -> None:
        """断开连接"""
        self._connected = False
    
    def _run_sync(self, func, *args, **kwargs):
        """在线程池中运行同步函数"""
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(func, *args, **kwargs)
            return future.result()
    
    async def get_kline(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[KlineData]:
        """获取K线数据
        
        Args:
            symbol: 股票代码，如 "000001" (不需要后缀)
            interval: K线周期
            start_time: 开始时间
            end_time: 结束时间
            limit: 返回条数限制
        """
        import pandas as pd
        
        # AKShare股票代码不带后缀
        code = symbol.split(".")[0] if "." in symbol else symbol
        
        # 日线数据
        if interval == "1d":
            df = await asyncio.to_thread(
                self.ak.stock_zh_a_hist,
                symbol=code,
                period="daily",
                start_date=start_time.strftime("%Y%m%d") if start_time else "19700101",
                end_date=end_time.strftime("%Y%m%d") if end_time else "20500101",
                adjust="qfq"  # 前复权
            )
        elif interval in ["1m", "5m", "15m", "30m", "60m"]:
            period_map = {
                "1m": "1",
                "5m": "5",
                "15m": "15",
                "30m": "30",
                "60m": "60",
            }
            df = await asyncio.to_thread(
                self.ak.stock_zh_a_hist_min_em,
                symbol=code,
                period=period_map.get(interval, "1"),
                adjust="qfq"
            )
        else:
            raise DataSourceError(f"Unsupported interval: {interval}", source="AKShare")
        
        if df is None or df.empty:
            return []
        
        # 限制返回数量
        if len(df) > limit:
            df = df.tail(limit)
        
        klines = []
        for _, row in df.iterrows():
            klines.append(KlineData(
                timestamp=pd.to_datetime(row["日期"]).to_pydatetime().replace(tzinfo=timezone.utc),
                open=Decimal(str(row["开盘"])),
                high=Decimal(str(row["最高"])),
                low=Decimal(str(row["最低"])),
                close=Decimal(str(row["收盘"])),
                volume=Decimal(str(row["成交量"])),
                quote_volume=Decimal(str(row.get("成交额", 0))),
            ))
        
        return klines
    
    async def get_tick(self, symbol: str, limit: int = 100) -> List[TickData]:
        """获取Tick数据"""
        import pandas as pd
        
        code = symbol.split(".")[0] if "." in symbol else symbol
        
        # 获取今日分时成交
        df = await asyncio.to_thread(
            self.ak.stock_zh_a_spot_em
        )
        
        # 找到对应股票
        row = df[df["代码"] == code]
        if row.empty:
            return []
        
        ticks = []
        ticks.append(TickData(
            timestamp=datetime.now(timezone.utc),
            symbol=symbol,
            price=Decimal(str(row["最新价"].values[0])),
            volume=Decimal("0"),
        ))
        
        return ticks
    
    async def get_symbols(self, market_type: Optional[MarketType] = None) -> List[SymbolInfo]:
        """获取股票列表"""
        df = await asyncio.to_thread(self.ak.stock_zh_a_spot_em)
        
        symbols = []
        for _, row in df.iterrows():
            code = row["代码"]
            # 根据代码判断交易所
            if code.startswith("6"):
                exchange = Exchange.SSE
                ts_code = f"{code}.SH"
            elif code.startswith("0") or code.startswith("3"):
                exchange = Exchange.SZSE
                ts_code = f"{code}.SZ"
            elif code.startswith("8") or code.startswith("4"):
                exchange = Exchange.BSE
                ts_code = f"{code}.BJ"
            else:
                exchange = Exchange.SSE
                ts_code = code
            
            symbols.append(SymbolInfo(
                symbol=ts_code,
                exchange=exchange,
                market_type=MarketType.STOCK,
                name=row.get("名称"),
            ))
        
        return symbols
    
    async def get_realtime_quote(self, symbol: str) -> Dict[str, Any]:
        """获取实时行情"""
        code = symbol.split(".")[0] if "." in symbol else symbol
        df = await asyncio.to_thread(
            self.ak.stock_zh_a_spot_em
        )
        row = df[df["代码"] == code]
        
        if row.empty:
            return {}
        
        return row.to_dict(orient="records")[0]
