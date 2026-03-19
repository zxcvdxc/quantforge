"""InfluxDB数据库管理器 - 时序数据存储"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from decimal import Decimal

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS, WriteOptions
from influxdb_client.domain.write_precision import WritePrecision

from .models import Kline, Tick


class InfluxDBManager:
    """InfluxDB时序数据库管理器"""
    
    def __init__(
        self,
        url: str = "http://localhost:8086",
        token: str = "",
        org: str = "quantforge",
        bucket: str = "market_data",
        timeout: int = 30000
    ):
        """
        初始化InfluxDB管理器
        
        Args:
            url: InfluxDB地址
            token: 访问令牌
            org: 组织名称
            bucket: 存储桶名称
            timeout: 超时时间(毫秒)
        """
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.timeout = timeout
        
        # 创建客户端
        self.client = InfluxDBClient(
            url=url,
            token=token,
            org=org,
            timeout=timeout
        )
        
        # 写入API
        self.write_api = self.client.write_api(
            write_options=WriteOptions(
                batch_size=1000,
                flush_interval=1000,
                jitter_interval=0,
                retry_interval=5000,
                max_retries=3,
                max_retry_delay=30000,
                exponential_base=2
            )
        )
        
        # 查询API
        self.query_api = self.client.query_api()
        
        # 删除API
        self.delete_api = self.client.delete_api()
        
        self._connected = False
    
    def connect(self) -> bool:
        """
        测试数据库连接
        
        Returns:
            是否连接成功
        """
        try:
            # 尝试获取组织信息来测试连接
            orgs_api = self.client.organizations_api()
            orgs = orgs_api.find_organizations()
            self._connected = True
            return True
        except Exception as e:
            print(f"InfluxDB连接失败: {e}")
            self._connected = False
            return False
    
    def disconnect(self) -> None:
        """断开连接"""
        if self.write_api:
            self.write_api.close()
        if self.client:
            self.client.close()
        self._connected = False
    
    def ensure_bucket(self) -> bool:
        """
        确保存储桶存在
        
        Returns:
            是否成功
        """
        try:
            buckets_api = self.client.buckets_api()
            bucket = buckets_api.find_bucket_by_name(self.bucket)
            
            if not bucket:
                # 创建存储桶，默认保留策略为永久
                buckets_api.create_bucket(
                    bucket_name=self.bucket,
                    org=self.org,
                    retention_rules=[]  # 永久保留
                )
            
            return True
        except Exception as e:
            print(f"确保存储桶失败: {e}")
            return False
    
    # ==================== K线数据管理 ====================
    
    def save_kline(self, kline: Kline) -> bool:
        """
        保存单条K线数据
        
        Args:
            kline: K线数据对象
            
        Returns:
            是否保存成功
        """
        try:
            point = Point("kline") \
                .tag("symbol", kline.symbol) \
                .tag("exchange", kline.exchange) \
                .tag("interval", kline.interval) \
                .field("open", float(kline.open)) \
                .field("high", float(kline.high)) \
                .field("low", float(kline.low)) \
                .field("close", float(kline.close)) \
                .field("volume", float(kline.volume)) \
                .field("quote_volume", float(kline.quote_volume)) \
                .field("trades", kline.trades) \
                .time(kline.timestamp, WritePrecision.NS)
            
            self.write_api.write(bucket=self.bucket, record=point)
            return True
        except Exception as e:
            print(f"保存K线数据失败: {e}")
            return False
    
    def save_klines(self, klines: List[Kline]) -> bool:
        """
        批量保存K线数据
        
        Args:
            klines: K线数据列表
            
        Returns:
            是否保存成功
        """
        try:
            points = []
            for kline in klines:
                point = Point("kline") \
                    .tag("symbol", kline.symbol) \
                    .tag("exchange", kline.exchange) \
                    .tag("interval", kline.interval) \
                    .field("open", float(kline.open)) \
                    .field("high", float(kline.high)) \
                    .field("low", float(kline.low)) \
                    .field("close", float(kline.close)) \
                    .field("volume", float(kline.volume)) \
                    .field("quote_volume", float(kline.quote_volume)) \
                    .field("trades", kline.trades) \
                    .time(kline.timestamp, WritePrecision.NS)
                points.append(point)
            
            self.write_api.write(bucket=self.bucket, record=points)
            return True
        except Exception as e:
            print(f"批量保存K线数据失败: {e}")
            return False
    
    def get_kline(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        timestamp: datetime
    ) -> Optional[Kline]:
        """
        获取单条K线数据
        
        Args:
            symbol: 交易对
            exchange: 交易所
            interval: 时间间隔
            timestamp: 时间戳
            
        Returns:
            K线数据对象或None
        """
        try:
            query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: {timestamp.isoformat()}, stop: {(timestamp + timedelta(minutes=1)).isoformat()})
                |> filter(fn: (r) => r._measurement == "kline")
                |> filter(fn: (r) => r.symbol == "{symbol}")
                |> filter(fn: (r) => r.exchange == "{exchange}")
                |> filter(fn: (r) => r.interval == "{interval}")
                |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
            '''
            
            tables = self.query_api.query(query, org=self.org)
            
            for table in tables:
                for record in table.records:
                    return self._record_to_kline(record)
            
            return None
        except Exception as e:
            print(f"获取K线数据失败: {e}")
            return None
    
    def query_klines(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[Kline]:
        """
        查询K线数据范围
        
        Args:
            symbol: 交易对
            exchange: 交易所
            interval: 时间间隔
            start_time: 开始时间
            end_time: 结束时间(默认为现在)
            limit: 限制数量
            
        Returns:
            K线数据列表
        """
        try:
            if end_time is None:
                end_time = datetime.utcnow()
            
            query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: {start_time.isoformat()}, stop: {end_time.isoformat()})
                |> filter(fn: (r) => r._measurement == "kline")
                |> filter(fn: (r) => r.symbol == "{symbol}")
                |> filter(fn: (r) => r.exchange == "{exchange}")
                |> filter(fn: (r) => r.interval == "{interval}")
                |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
                |> limit(n: {limit})
            '''
            
            tables = self.query_api.query(query, org=self.org)
            
            klines = []
            for table in tables:
                for record in table.records:
                    kline = self._record_to_kline(record)
                    if kline:
                        klines.append(kline)
            
            return klines
        except Exception as e:
            print(f"查询K线数据失败: {e}")
            return []
    
    def get_latest_kline(
        self,
        symbol: str,
        exchange: str,
        interval: str
    ) -> Optional[Kline]:
        """
        获取最新K线数据
        
        Args:
            symbol: 交易对
            exchange: 交易所
            interval: 时间间隔
            
        Returns:
            最新K线数据或None
        """
        try:
            query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: -7d)
                |> filter(fn: (r) => r._measurement == "kline")
                |> filter(fn: (r) => r.symbol == "{symbol}")
                |> filter(fn: (r) => r.exchange == "{exchange}")
                |> filter(fn: (r) => r.interval == "{interval}")
                |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
                |> last()
            '''
            
            tables = self.query_api.query(query, org=self.org)
            
            for table in tables:
                for record in table.records:
                    return self._record_to_kline(record)
            
            return None
        except Exception as e:
            print(f"获取最新K线数据失败: {e}")
            return None
    
    def _record_to_kline(self, record) -> Optional[Kline]:
        """将查询记录转换为Kline对象"""
        try:
            values = record.values
            return Kline(
                symbol=values.get('symbol', ''),
                exchange=values.get('exchange', ''),
                interval=values.get('interval', ''),
                timestamp=record.get_time(),
                open=Decimal(str(values.get('open', 0))),
                high=Decimal(str(values.get('high', 0))),
                low=Decimal(str(values.get('low', 0))),
                close=Decimal(str(values.get('close', 0))),
                volume=Decimal(str(values.get('volume', 0))),
                quote_volume=Decimal(str(values.get('quote_volume', 0))),
                trades=int(values.get('trades', 0))
            )
        except Exception as e:
            print(f"转换Kline记录失败: {e}")
            return None
    
    # ==================== Tick数据管理 ====================
    
    def save_tick(self, tick: Tick) -> bool:
        """
        保存单条Tick数据
        
        Args:
            tick: Tick数据对象
            
        Returns:
            是否保存成功
        """
        try:
            point = Point("tick") \
                .tag("symbol", tick.symbol) \
                .tag("exchange", tick.exchange) \
                .tag("side", tick.side) \
                .field("price", float(tick.price)) \
                .field("quantity", float(tick.quantity)) \
                .field("trade_id", tick.trade_id) \
                .time(tick.timestamp, WritePrecision.NS)
            
            self.write_api.write(bucket=self.bucket, record=point)
            return True
        except Exception as e:
            print(f"保存Tick数据失败: {e}")
            return False
    
    def save_ticks(self, ticks: List[Tick]) -> bool:
        """
        批量保存Tick数据
        
        Args:
            ticks: Tick数据列表
            
        Returns:
            是否保存成功
        """
        try:
            points = []
            for tick in ticks:
                point = Point("tick") \
                    .tag("symbol", tick.symbol) \
                    .tag("exchange", tick.exchange) \
                    .tag("side", tick.side) \
                    .field("price", float(tick.price)) \
                    .field("quantity", float(tick.quantity)) \
                    .field("trade_id", tick.trade_id) \
                    .time(tick.timestamp, WritePrecision.NS)
                points.append(point)
            
            self.write_api.write(bucket=self.bucket, record=points)
            return True
        except Exception as e:
            print(f"批量保存Tick数据失败: {e}")
            return False
    
    def query_ticks(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        side: Optional[str] = None,
        limit: int = 10000
    ) -> List[Tick]:
        """
        查询Tick数据范围
        
        Args:
            symbol: 交易对
            exchange: 交易所
            start_time: 开始时间
            end_time: 结束时间(默认为现在)
            side: 买卖方向筛选
            limit: 限制数量
            
        Returns:
            Tick数据列表
        """
        try:
            if end_time is None:
                end_time = datetime.utcnow()
            
            side_filter = f'|> filter(fn: (r) => r.side == "{side}")' if side else ''
            
            query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: {start_time.isoformat()}, stop: {end_time.isoformat()})
                |> filter(fn: (r) => r._measurement == "tick")
                |> filter(fn: (r) => r.symbol == "{symbol}")
                |> filter(fn: (r) => r.exchange == "{exchange}")
                {side_filter}
                |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
                |> limit(n: {limit})
            '''
            
            tables = self.query_api.query(query, org=self.org)
            
            ticks = []
            for table in tables:
                for record in table.records:
                    tick = self._record_to_tick(record)
                    if tick:
                        ticks.append(tick)
            
            return ticks
        except Exception as e:
            print(f"查询Tick数据失败: {e}")
            return []
    
    def get_latest_tick(
        self,
        symbol: str,
        exchange: str
    ) -> Optional[Tick]:
        """
        获取最新Tick数据
        
        Args:
            symbol: 交易对
            exchange: 交易所
            
        Returns:
            最新Tick数据或None
        """
        try:
            query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: -1h)
                |> filter(fn: (r) => r._measurement == "tick")
                |> filter(fn: (r) => r.symbol == "{symbol}")
                |> filter(fn: (r) => r.exchange == "{exchange}")
                |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
                |> last()
            '''
            
            tables = self.query_api.query(query, org=self.org)
            
            for table in tables:
                for record in table.records:
                    return self._record_to_tick(record)
            
            return None
        except Exception as e:
            print(f"获取最新Tick数据失败: {e}")
            return None
    
    def _record_to_tick(self, record) -> Optional[Tick]:
        """将查询记录转换为Tick对象"""
        try:
            values = record.values
            return Tick(
                symbol=values.get('symbol', ''),
                exchange=values.get('exchange', ''),
                timestamp=record.get_time(),
                price=Decimal(str(values.get('price', 0))),
                quantity=Decimal(str(values.get('quantity', 0))),
                side=values.get('side', ''),
                trade_id=values.get('trade_id', '')
            )
        except Exception as e:
            print(f"转换Tick记录失败: {e}")
            return None
    
    # ==================== 数据删除 ====================
    
    def delete_klines(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        start_time: datetime,
        end_time: datetime
    ) -> bool:
        """
        删除K线数据
        
        Args:
            symbol: 交易对
            exchange: 交易所
            interval: 时间间隔
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            是否删除成功
        """
        try:
            predicate = f'_measurement="kline" AND symbol="{symbol}" AND exchange="{exchange}" AND interval="{interval}"'
            self.delete_api.delete(
                start=start_time,
                stop=end_time,
                predicate=predicate,
                bucket=self.bucket,
                org=self.org
            )
            return True
        except Exception as e:
            print(f"删除K线数据失败: {e}")
            return False
    
    def delete_ticks(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime
    ) -> bool:
        """
        删除Tick数据
        
        Args:
            symbol: 交易对
            exchange: 交易所
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            是否删除成功
        """
        try:
            predicate = f'_measurement="tick" AND symbol="{symbol}" AND exchange="{exchange}"'
            self.delete_api.delete(
                start=start_time,
                stop=end_time,
                predicate=predicate,
                bucket=self.bucket,
                org=self.org
            )
            return True
        except Exception as e:
            print(f"删除Tick数据失败: {e}")
            return False
    
    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected