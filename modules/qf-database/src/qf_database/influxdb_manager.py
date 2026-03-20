"""InfluxDB数据库管理器 - 时序数据存储

性能优化特性:
- 优化的批量写入配置 (batch_size, flush_interval)
- 重试机制配置
- 异步写入支持
- 连接池管理
"""
from typing import Optional, List, Dict, Any, Union, Tuple
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
import time

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS, ASYNCHRONOUS, WriteOptions
from influxdb_client.client.write_api import WriteApi
from influxdb_client.domain.write_precision import WritePrecision
from influxdb_client.rest import ApiException

from .models import Kline, Tick

logger = logging.getLogger(__name__)


class InfluxDBManager:
    """InfluxDB时序数据库管理器 - 优化版
    
    批量写入优化配置:
    - batch_size: 批次大小，默认5000
    - flush_interval: 刷新间隔(ms)，默认1000
    - jitter_interval: 抖动间隔(ms)，默认0
    - retry_interval: 重试间隔(ms)，默认5000
    - max_retries: 最大重试次数，默认5
    - max_retry_delay: 最大重试延迟(ms)，默认30000
    - exponential_base: 指数退避基数，默认2
    
    性能特性:
    - 批量写入优化
    - 异步写入支持
    - 智能重试机制
    - 连接池管理
    """
    
    # 默认写入配置
    DEFAULT_BATCH_SIZE = 5000
    DEFAULT_FLUSH_INTERVAL = 1000  # ms
    DEFAULT_RETRY_INTERVAL = 5000  # ms
    DEFAULT_MAX_RETRIES = 5
    DEFAULT_MAX_RETRY_DELAY = 30000  # ms
    DEFAULT_EXPONENTIAL_BASE = 2
    
    def __init__(
        self,
        url: str = "http://localhost:8086",
        token: str = "",
        org: str = "quantforge",
        bucket: str = "market_data",
        timeout: int = 30000,
        # 批量写入配置
        batch_size: int = None,
        flush_interval: int = None,
        enable_gzip: bool = True,
        # 重试配置
        max_retries: int = None,
        retry_interval: int = None,
        max_retry_delay: int = None,
        exponential_base: int = None,
        # 模式配置
        write_mode: str = "batch"  # "batch", "sync", "async"
    ):
        """
        初始化InfluxDB管理器
        
        Args:
            url: InfluxDB地址
            token: 访问令牌
            org: 组织名称
            bucket: 存储桶名称
            timeout: 超时时间(毫秒)
            batch_size: 批次大小 (默认5000)
            flush_interval: 刷新间隔毫秒 (默认1000)
            enable_gzip: 是否启用GZIP压缩
            max_retries: 最大重试次数 (默认5)
            retry_interval: 重试间隔毫秒 (默认5000)
            max_retry_delay: 最大重试延迟毫秒 (默认30000)
            exponential_base: 指数退避基数 (默认2)
            write_mode: 写入模式 "batch"/"sync"/"async"
        """
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.timeout = timeout
        self.write_mode = write_mode
        
        # 写入统计
        self._write_stats = {
            "total_points": 0,
            "total_batches": 0,
            "failed_writes": 0,
            "last_write_time": None
        }
        
        # 使用默认配置
        batch_size = batch_size or self.DEFAULT_BATCH_SIZE
        flush_interval = flush_interval or self.DEFAULT_FLUSH_INTERVAL
        max_retries = max_retries or self.DEFAULT_MAX_RETRIES
        retry_interval = retry_interval or self.DEFAULT_RETRY_INTERVAL
        max_retry_delay = max_retry_delay or self.DEFAULT_MAX_RETRY_DELAY
        exponential_base = exponential_base or self.DEFAULT_EXPONENTIAL_BASE
        
        # 创建客户端
        self.client = InfluxDBClient(
            url=url,
            token=token,
            org=org,
            timeout=timeout,
            enable_gzip=enable_gzip
        )
        
        # 根据模式配置写入API
        if write_mode == "sync":
            self.write_api: WriteApi = self.client.write_api(write_options=SYNCHRONOUS)
        elif write_mode == "async":
            self.write_api: WriteApi = self.client.write_api(write_options=ASYNCHRONOUS)
        else:  # batch mode (default)
            self.write_api: WriteApi = self.client.write_api(
                write_options=WriteOptions(
                    batch_size=batch_size,
                    flush_interval=flush_interval,
                    jitter_interval=0,
                    retry_interval=retry_interval,
                    max_retries=max_retries,
                    max_retry_delay=max_retry_delay,
                    exponential_base=exponential_base
                )
            )
        
        # 查询API
        self.query_api = self.client.query_api()
        
        # 删除API
        self.delete_api = self.client.delete_api()
        
        self._connected = False
        
        logger.info(f"InfluxDBManager initialized with batch_size={batch_size}, mode={write_mode}")
    
    def connect(self) -> bool:
        """
        测试数据库连接
        
        Returns:
            是否连接成功
        """
        try:
            # 尝试获取组织信息来测试连接
            start_time = time.time()
            orgs_api = self.client.organizations_api()
            orgs = orgs_api.find_organizations()
            
            latency = time.time() - start_time
            self._connected = True
            
            logger.debug(f"InfluxDB connection successful, latency={latency*1000:.2f}ms")
            return True
            
        except ApiException as e:
            logger.error(f"InfluxDB connection failed (ApiException): {e}")
            self._connected = False
            return False
        except Exception as e:
            logger.error(f"InfluxDB connection failed: {e}")
            self._connected = False
            return False
    
    def disconnect(self) -> None:
        """断开连接并刷新所有待写入数据"""
        try:
            if self.write_api:
                self.write_api.close()
            if self.client:
                self.client.close()
            logger.info("InfluxDB connection closed")
        except Exception as e:
            logger.warning(f"Error during disconnect: {e}")
        finally:
            self._connected = False
    
    def health_check(self) -> Tuple[bool, float, Optional[str]]:
        """
        健康检查
        
        Returns:
            (是否健康, 延迟毫秒, 错误信息)
        """
        try:
            start_time = time.time()
            self.client.ready()
            latency = (time.time() - start_time) * 1000
            return True, latency, None
        except Exception as e:
            return False, 0.0, str(e)
    
    def get_write_stats(self) -> Dict[str, Any]:
        """获取写入统计信息"""
        return self._write_stats.copy()
    
    def flush(self) -> None:
        """强制刷新所有待写入数据"""
        if self.write_api:
            self.write_api.flush()
    
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
            
            # 更新统计
            self._write_stats["total_points"] += 1
            self._write_stats["last_write_time"] = datetime.now(timezone.utc)
            
            return True
        except ApiException as e:
            logger.error(f"InfluxDB API error saving kline: {e}")
            self._write_stats["failed_writes"] += 1
            return False
        except Exception as e:
            logger.error(f"保存K线数据失败: {e}")
            self._write_stats["failed_writes"] += 1
            return False
    
    def save_klines(self, klines: List[Kline]) -> bool:
        """
        批量保存K线数据 - 优化版
        
        Args:
            klines: K线数据列表
            
        Returns:
            是否保存成功
        """
        if not klines:
            return True
        
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
            
            # 更新统计
            self._write_stats["total_points"] += len(points)
            self._write_stats["total_batches"] += 1
            self._write_stats["last_write_time"] = datetime.now(timezone.utc)
            
            logger.debug(f"Batch saved {len(points)} klines to InfluxDB")
            return True
            
        except ApiException as e:
            logger.error(f"InfluxDB API error saving klines batch: {e}")
            self._write_stats["failed_writes"] += len(klines)
            return False
        except Exception as e:
            logger.error(f"批量保存K线数据失败: {e}")
            self._write_stats["failed_writes"] += len(klines)
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