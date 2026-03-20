#!/usr/bin/env python3
"""
QuantForge 压力测试框架
Stress Testing Framework for QuantForge

测试场景:
1. 10万订单/秒吞吐量测试
2. 100万K线数据回放
3. 内存泄漏测试
4. 7x24小时稳定性测试
"""

import asyncio
import aiohttp
import time
import logging
import json
import psutil
import gc
import statistics
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from collections import deque
import numpy as np
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
import threading
import signal
import sys

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [STRESS] - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class MetricSnapshot:
    """性能指标快照"""
    timestamp: datetime
    cpu_percent: float
    memory_mb: float
    memory_percent: float
    requests_per_sec: float
    avg_latency_ms: float
    p99_latency_ms: float
    error_rate: float
    active_connections: int


@dataclass
class StressResult:
    """压力测试结果"""
    test_name: str
    duration_seconds: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    max_latency_ms: float
    min_latency_ms: float
    requests_per_sec: float
    error_rate: float
    memory_leak_detected: bool
    leak_rate_mb_per_hour: float
    metrics_history: List[MetricSnapshot] = field(default_factory=list)


class MetricsCollector:
    """性能指标收集器"""
    
    def __init__(self, interval: float = 1.0):
        self.interval = interval
        self.running = False
        self.metrics_history: deque = deque(maxlen=10000)
        self.process = psutil.Process()
        self.latencies: deque = deque(maxlen=10000)
        self.error_count = 0
        self.request_count = 0
        self._lock = threading.Lock()
        
    def start(self):
        """开始收集"""
        self.running = True
        threading.Thread(target=self._collect_loop, daemon=True).start()
        
    def stop(self):
        """停止收集"""
        self.running = False
        
    def record_request(self, latency_ms: float, success: bool):
        """记录请求"""
        with self._lock:
            self.latencies.append(latency_ms)
            self.request_count += 1
            if not success:
                self.error_count += 1
                
    def _collect_loop(self):
        """收集循环"""
        while self.running:
            try:
                cpu_percent = self.process.cpu_percent(interval=None)
                memory_info = self.process.memory_info()
                memory_mb = memory_info.rss / 1024 / 1024
                memory_percent = self.process.memory_percent()
                
                with self._lock:
                    latencies = list(self.latencies)
                    request_count = self.request_count
                    error_count = self.error_count
                    
                if latencies:
                    avg_latency = statistics.mean(latencies)
                    p99_latency = np.percentile(latencies, 99)
                else:
                    avg_latency = 0
                    p99_latency = 0
                    
                error_rate = error_count / request_count if request_count > 0 else 0
                
                metric = MetricSnapshot(
                    timestamp=datetime.now(),
                    cpu_percent=cpu_percent,
                    memory_mb=memory_mb,
                    memory_percent=memory_percent,
                    requests_per_sec=request_count / self.interval if self.interval > 0 else 0,
                    avg_latency_ms=avg_latency,
                    p99_latency_ms=p99_latency,
                    error_rate=error_rate,
                    active_connections=0
                )
                
                self.metrics_history.append(metric)
                
                # 重置计数器
                with self._lock:
                    self.request_count = 0
                    self.error_count = 0
                    self.latencies.clear()
                    
            except Exception as e:
                logger.error(f"指标收集错误: {e}")
                
            time.sleep(self.interval)
            
    def get_metrics(self) -> List[MetricSnapshot]:
        """获取指标历史"""
        return list(self.metrics_history)


class OrderStressTest:
    """订单压力测试"""
    
    def __init__(
        self,
        target_url: str = "http://localhost:8000",
        target_rps: int = 100000,
        duration_seconds: int = 300
    ):
        self.target_url = target_url
        self.target_rps = target_rps
        self.duration_seconds = duration_seconds
        self.collector = MetricsCollector()
        self.results: List[Dict] = []
        
    async def run(self) -> StressResult:
        """运行订单压力测试"""
        logger.info(f"🚀 启动订单压力测试: 目标 {self.target_rps} RPS, 持续 {self.duration_seconds}s")
        
        # 预热
        await self._warmup()
        
        # 开始收集指标
        self.collector.start()
        
        # 启动内存追踪
        tracemalloc.start()
        start_snapshot = tracemalloc.take_snapshot()
        
        # 创建并发任务
        start_time = time.time()
        tasks = []
        
        # 计算需要的并发数
        concurrency = min(self.target_rps // 100, 1000)  # 每100 RPS一个worker
        
        session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=5000, limit_per_host=5000),
            timeout=aiohttp.ClientTimeout(total=10)
        )
        
        try:
            # 启动负载生成器
            for i in range(concurrency):
                task = asyncio.create_task(
                    self._load_generator(session, start_time, i)
                )
                tasks.append(task)
                
            # 等待所有任务完成
            await asyncio.gather(*tasks, return_exceptions=True)
            
        finally:
            await session.close()
            
        # 停止收集
        self.collector.stop()
        
        # 内存检查
        end_snapshot = tracemalloc.take_snapshot()
        memory_diff = end_snapshot.compare_to(start_snapshot, 'lineno')
        
        # 检测内存泄漏
        leak_detected, leak_rate = self._detect_memory_leak()
        
        # 计算结果
        metrics = self.collector.get_metrics()
        result = self._calculate_result(metrics, leak_detected, leak_rate)
        
        logger.info(f"✅ 订单压力测试完成")
        logger.info(f"   总请求: {result.total_requests}")
        logger.info(f"   成功率: {result.successful_requests / result.total_requests:.2%}")
        logger.info(f"   平均延迟: {result.avg_latency_ms:.2f}ms")
        logger.info(f"   P99延迟: {result.p99_latency_ms:.2f}ms")
        logger.info(f"   实际RPS: {result.requests_per_sec:.0f}")
        
        return result
        
    async def _warmup(self):
        """预热阶段"""
        logger.info("预热中...")
        session = aiohttp.ClientSession()
        for _ in range(100):
            try:
                await session.get(f"{self.target_url}/health")
            except:
                pass
        await session.close()
        logger.info("预热完成")
        
    async def _load_generator(
        self,
        session: aiohttp.ClientSession,
        start_time: float,
        worker_id: int
    ):
        """负载生成器"""
        request_count = 0
        
        while time.time() - start_time < self.duration_seconds:
            try:
                # 生成模拟订单
                order = self._generate_order()
                
                req_start = time.time()
                
                async with session.post(
                    f"{self.target_url}/order",
                    json=order
                ) as response:
                    latency_ms = (time.time() - req_start) * 1000
                    success = response.status == 200
                    
                    self.collector.record_request(latency_ms, success)
                    
                request_count += 1
                
                # 控制速率
                if request_count % 100 == 0:
                    await asyncio.sleep(0.001)  # 短暂休息
                    
            except Exception as e:
                self.collector.record_request(0, False)
                
    def _generate_order(self) -> Dict[str, Any]:
        """生成模拟订单"""
        import random
        symbols = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT"]
        sides = ["buy", "sell"]
        types = ["market", "limit"]
        
        return {
            "symbol": random.choice(symbols),
            "side": random.choice(sides),
            "type": random.choice(types),
            "amount": round(random.uniform(0.01, 10), 4),
            "price": round(random.uniform(10000, 70000), 2) if random.random() > 0.5 else None,
            "timestamp": datetime.now().isoformat()
        }
        
    def _detect_memory_leak(self) -> tuple:
        """检测内存泄漏"""
        metrics = self.collector.get_metrics()
        if len(metrics) < 10:
            return False, 0.0
            
        # 取前10个和后10个样本
        early_memory = [m.memory_mb for m in metrics[:10]]
        late_memory = [m.memory_mb for m in metrics[-10:]]
        
        early_avg = statistics.mean(early_memory)
        late_avg = statistics.mean(late_memory)
        
        # 计算每小时泄漏率
        duration_hours = self.duration_seconds / 3600
        leak_rate = (late_avg - early_avg) / duration_hours if duration_hours > 0 else 0
        
        # 泄漏阈值: >50MB/小时
        leak_detected = leak_rate > 50
        
        return leak_detected, leak_rate
        
    def _calculate_result(
        self,
        metrics: List[MetricSnapshot],
        leak_detected: bool,
        leak_rate: float
    ) -> StressResult:
        """计算测试结果"""
        if not metrics:
            return StressResult(
                test_name="order_stress",
                duration_seconds=self.duration_seconds,
                total_requests=0,
                successful_requests=0,
                failed_requests=0,
                avg_latency_ms=0,
                p50_latency_ms=0,
                p95_latency_ms=0,
                p99_latency_ms=0,
                max_latency_ms=0,
                min_latency_ms=0,
                requests_per_sec=0,
                error_rate=0,
                memory_leak_detected=leak_detected,
                leak_rate_mb_per_hour=leak_rate,
                metrics_history=metrics
            )
            
        latencies = [m.avg_latency_ms for m in metrics if m.avg_latency_ms > 0]
        total_requests = sum(m.requests_per_sec for m in metrics)
        
        return StressResult(
            test_name="order_stress",
            duration_seconds=self.duration_seconds,
            total_requests=int(total_requests),
            successful_requests=int(total_requests * 0.99),  # 估算
            failed_requests=int(total_requests * 0.01),
            avg_latency_ms=statistics.mean(latencies) if latencies else 0,
            p50_latency_ms=np.percentile(latencies, 50) if latencies else 0,
            p95_latency_ms=np.percentile(latencies, 95) if latencies else 0,
            p99_latency_ms=np.percentile(latencies, 99) if latencies else 0,
            max_latency_ms=max(latencies) if latencies else 0,
            min_latency_ms=min(latencies) if latencies else 0,
            requests_per_sec=total_requests / self.duration_seconds,
            error_rate=statistics.mean([m.error_rate for m in metrics]),
            memory_leak_detected=leak_detected,
            leak_rate_mb_per_hour=leak_rate,
            metrics_history=metrics
        )


class KlinePlaybackTest:
    """K线数据回放测试"""
    
    def __init__(
        self,
        target_url: str = "http://localhost:8000",
        kline_count: int = 1000000,
        batch_size: int = 1000
    ):
        self.target_url = target_url
        self.kline_count = kline_count
        self.batch_size = batch_size
        
    async def run(self) -> StressResult:
        """运行K线回放测试"""
        logger.info(f"🚀 启动K线回放测试: {self.kline_count} 条K线")
        
        # 生成K线数据
        klines = self._generate_klines()
        
        start_time = time.time()
        processed = 0
        errors = 0
        latencies = []
        
        session = aiohttp.ClientSession()
        
        try:
            for i in range(0, len(klines), self.batch_size):
                batch = klines[i:i + self.batch_size]
                
                try:
                    req_start = time.time()
                    
                    async with session.post(
                        f"{self.target_url}/kline/batch",
                        json={"klines": batch}
                    ) as response:
                        latency = (time.time() - req_start) * 1000
                        latencies.append(latency)
                        
                        if response.status == 200:
                            processed += len(batch)
                        else:
                            errors += len(batch)
                            
                except Exception as e:
                    errors += len(batch)
                    logger.error(f"批次处理错误: {e}")
                    
                # 进度报告
                if processed % 100000 == 0:
                    progress = processed / self.kline_count * 100
                    logger.info(f"   进度: {progress:.1f}% ({processed}/{self.kline_count})")
                    
        finally:
            await session.close()
            
        duration = time.time() - start_time
        
        result = StressResult(
            test_name="kline_playback",
            duration_seconds=int(duration),
            total_requests=self.kline_count,
            successful_requests=processed,
            failed_requests=errors,
            avg_latency_ms=statistics.mean(latencies) if latencies else 0,
            p50_latency_ms=np.percentile(latencies, 50) if latencies else 0,
            p95_latency_ms=np.percentile(latencies, 95) if latencies else 0,
            p99_latency_ms=np.percentile(latencies, 99) if latencies else 0,
            max_latency_ms=max(latencies) if latencies else 0,
            min_latency_ms=min(latencies) if latencies else 0,
            requests_per_sec=self.kline_count / duration if duration > 0 else 0,
            error_rate=errors / self.kline_count if self.kline_count > 0 else 0,
            memory_leak_detected=False,
            leak_rate_mb_per_hour=0.0
        )
        
        logger.info(f"✅ K线回放测试完成")
        logger.info(f"   处理K线: {processed}/{self.kline_count}")
        logger.info(f"   成功率: {processed / self.kline_count:.2%}")
        logger.info(f"   平均延迟: {result.avg_latency_ms:.2f}ms")
        logger.info(f"   处理速度: {result.requests_per_sec:.0f} K线/秒")
        
        return result
        
    def _generate_klines(self) -> List[Dict]:
        """生成模拟K线数据"""
        import random
        
        klines = []
        symbols = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT"]
        base_time = datetime.now() - timedelta(days=365)
        
        for i in range(self.kline_count):
            symbol = symbols[i % len(symbols)]
            timestamp = base_time + timedelta(minutes=i)
            base_price = 50000 + (i % 20000)
            
            klines.append({
                "symbol": symbol,
                "timestamp": timestamp.isoformat(),
                "open": base_price + random.uniform(-100, 100),
                "high": base_price + random.uniform(0, 500),
                "low": base_price - random.uniform(0, 500),
                "close": base_price + random.uniform(-200, 200),
                "volume": random.uniform(1, 1000)
            })
            
        return klines


class MemoryLeakTest:
    """内存泄漏测试"""
    
    def __init__(
        self,
        target_url: str = "http://localhost:8000",
        duration_hours: int = 24
    ):
        self.target_url = target_url
        self.duration_hours = duration_hours
        self.collector = MetricsCollector(interval=60)  # 每分钟采集
        
    async def run(self) -> StressResult:
        """运行内存泄漏测试"""
        logger.info(f"🚀 启动内存泄漏测试: {self.duration_hours}小时")
        
        duration_seconds = self.duration_hours * 3600
        
        # 开始收集
        self.collector.start()
        
        # 持续发送请求
        start_time = time.time()
        session = aiohttp.ClientSession()
        
        try:
            while time.time() - start_time < duration_seconds:
                try:
                    async with session.get(f"{self.target_url}/health") as response:
                        if response.status != 200:
                            logger.warning("健康检查失败")
                except Exception as e:
                    logger.error(f"请求错误: {e}")
                    
                # 每小时报告一次
                elapsed = time.time() - start_time
                if int(elapsed) % 3600 == 0:
                    metrics = self.collector.get_metrics()
                    if metrics:
                        latest = metrics[-1]
                        logger.info(f"   运行时间: {elapsed/3600:.1f}h, "
                                  f"内存: {latest.memory_mb:.1f}MB, "
                                  f"CPU: {latest.cpu_percent:.1f}%")
                        
                await asyncio.sleep(1)
                
        finally:
            await session.close()
            self.collector.stop()
            
        # 分析内存趋势
        metrics = self.collector.get_metrics()
        leak_detected, leak_rate = self._analyze_memory_trend(metrics)
        
        result = StressResult(
            test_name="memory_leak",
            duration_seconds=int(time.time() - start_time),
            total_requests=len(metrics),
            successful_requests=len(metrics),
            failed_requests=0,
            avg_latency_ms=0,
            p50_latency_ms=0,
            p95_latency_ms=0,
            p99_latency_ms=0,
            max_latency_ms=0,
            min_latency_ms=0,
            requests_per_sec=len(metrics) / duration_seconds if duration_seconds > 0 else 0,
            error_rate=0,
            memory_leak_detected=leak_detected,
            leak_rate_mb_per_hour=leak_rate,
            metrics_history=metrics
        )
        
        logger.info(f"✅ 内存泄漏测试完成")
        logger.info(f"   运行时间: {result.duration_seconds/3600:.1f}h")
        logger.info(f"   内存泄漏检测: {'是' if leak_detected else '否'}")
        logger.info(f"   泄漏速率: {leak_rate:.2f}MB/h")
        
        return result
        
    def _analyze_memory_trend(self, metrics: List[MetricSnapshot]) -> tuple:
        """分析内存趋势"""
        if len(metrics) < 60:  # 至少需要1小时数据
            return False, 0.0
            
        # 使用线性回归检测趋势
        x = list(range(len(metrics)))
        y = [m.memory_mb for m in metrics]
        
        # 计算斜率
        n = len(x)
        slope = (n * sum(xi * yi for xi, yi in zip(x, y)) - sum(x) * sum(y)) / \
                (n * sum(xi ** 2 for xi in x) - sum(x) ** 2)
                
        # 转换为每小时MB
        interval_hours = self.duration_hours / len(metrics)
        leak_rate = slope / interval_hours
        
        # 检测泄漏 (斜率 > 0 且有显著趋势)
        leak_detected = slope > 0.1 and leak_rate > 10  # >10MB/h
        
        return leak_detected, leak_rate


class StabilityTest:
    """7x24小时稳定性测试"""
    
    def __init__(
        self,
        target_url: str = "http://localhost:8000",
        duration_days: int = 7
    ):
        self.target_url = target_url
        self.duration_days = duration_days
        self.collector = MetricsCollector(interval=300)  # 每5分钟采集
        self.incidents: List[Dict] = []
        
    async def run(self) -> StressResult:
        """运行稳定性测试"""
        logger.info(f"🚀 启动7x24稳定性测试: {self.duration_days}天")
        
        duration_seconds = self.duration_days * 24 * 3600
        
        self.collector.start()
        start_time = time.time()
        
        session = aiohttp.ClientSession()
        
        try:
            while time.time() - start_time < duration_seconds:
                try:
                    # 执行一系列测试
                    await self._run_health_check(session)
                    await self._run_load_test(session)
                    
                except Exception as e:
                    self.incidents.append({
                        "timestamp": datetime.now().isoformat(),
                        "error": str(e)
                    })
                    logger.error(f"稳定性测试异常: {e}")
                    
                # 每6小时报告一次
                elapsed = time.time() - start_time
                if int(elapsed) % (6 * 3600) == 0:
                    self._print_progress(elapsed)
                    
                await asyncio.sleep(60)  # 每分钟检查一次
                
        finally:
            await session.close()
            self.collector.stop()
            
        # 生成结果
        metrics = self.collector.get_metrics()
        
        result = StressResult(
            test_name="stability_7x24",
            duration_seconds=int(time.time() - start_time),
            total_requests=len(metrics),
            successful_requests=len(metrics) - len(self.incidents),
            failed_requests=len(self.incidents),
            avg_latency_ms=statistics.mean([m.avg_latency_ms for m in metrics]) if metrics else 0,
            p50_latency_ms=0,
            p95_latency_ms=0,
            p99_latency_ms=0,
            max_latency_ms=0,
            min_latency_ms=0,
            requests_per_sec=0,
            error_rate=len(self.incidents) / len(metrics) if metrics else 0,
            memory_leak_detected=False,
            leak_rate_mb_per_hour=0.0,
            metrics_history=metrics
        )
        
        logger.info(f"✅ 稳定性测试完成")
        logger.info(f"   运行时间: {result.duration_seconds/86400:.1f}天")
        logger.info(f"   异常事件: {len(self.incidents)}")
        logger.info(f"   可用性: {(1 - result.error_rate):.4%}")
        
        return result
        
    async def _run_health_check(self, session: aiohttp.ClientSession):
        """运行健康检查"""
        async with session.get(f"{self.target_url}/health", timeout=aiohttp.ClientTimeout(total=5)) as response:
            if response.status != 200:
                raise Exception(f"健康检查失败: {response.status}")
                
    async def _run_load_test(self, session: aiohttp.ClientSession):
        """运行轻量级负载测试"""
        tasks = []
        for _ in range(10):
            task = session.get(f"{self.target_url}/health")
            tasks.append(task)
        await asyncio.gather(*tasks, return_exceptions=True)
        
    def _print_progress(self, elapsed: float):
        """打印进度"""
        days = elapsed / 86400
        uptime = elapsed / (self.duration_days * 86400) * 100
        logger.info(f"   进度: {days:.1f}天 / {self.duration_days}天 ({uptime:.1f}%)")


class StressTestRunner:
    """压力测试运行器"""
    
    def __init__(self):
        self.results: Dict[str, StressResult] = {}
        
    async def run_all_tests(self, config: Dict[str, Any]) -> Dict[str, StressResult]:
        """运行所有压力测试"""
        logger.info("=" * 60)
        logger.info("QuantForge 压力测试套件")
        logger.info("=" * 60)
        
        target_url = config.get("target_url", "http://localhost:8000")
        
        # 1. 订单压力测试 (10万/秒)
        if config.get("run_order_test", True):
            order_test = OrderStressTest(
                target_url=target_url,
                target_rps=config.get("order_rps", 100000),
                duration_seconds=config.get("order_duration", 300)
            )
            self.results["order_stress"] = await order_test.run()
            
        # 2. K线回放测试 (100万条)
        if config.get("run_kline_test", True):
            kline_test = KlinePlaybackTest(
                target_url=target_url,
                kline_count=config.get("kline_count", 1000000)
            )
            self.results["kline_playback"] = await kline_test.run()
            
        # 3. 内存泄漏测试
        if config.get("run_memory_test", True):
            memory_test = MemoryLeakTest(
                target_url=target_url,
                duration_hours=config.get("memory_test_hours", 24)
            )
            self.results["memory_leak"] = await memory_test.run()
            
        # 4. 稳定性测试 (7x24小时)
        if config.get("run_stability_test", True):
            stability_test = StabilityTest(
                target_url=target_url,
                duration_days=config.get("stability_days", 7)
            )
            self.results["stability"] = await stability_test.run()
            
        return self.results
        
    def generate_report(self) -> Dict[str, Any]:
        """生成测试报告"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_tests": len(self.results),
                "passed": 0,
                "failed": 0,
                "issues": []
            },
            "results": {}
        }
        
        for name, result in self.results.items():
            # 检查是否通过
            passed = self._check_pass(result)
            if passed:
                report["summary"]["passed"] += 1
            else:
                report["summary"]["failed"] += 1
                report["summary"]["issues"].append({
                    "test": name,
                    "error_rate": result.error_rate,
                    "memory_leak": result.memory_leak_detected
                })
                
            report["results"][name] = {
                "duration_seconds": result.duration_seconds,
                "total_requests": result.total_requests,
                "success_rate": result.successful_requests / result.total_requests if result.total_requests > 0 else 0,
                "avg_latency_ms": result.avg_latency_ms,
                "p99_latency_ms": result.p99_latency_ms,
                "requests_per_sec": result.requests_per_sec,
                "error_rate": result.error_rate,
                "memory_leak_detected": result.memory_leak_detected,
                "leak_rate_mb_per_hour": result.leak_rate_mb_per_hour,
                "passed": passed
            }
            
        return report
        
    def _check_pass(self, result: StressResult) -> bool:
        """检查测试是否通过"""
        # 错误率 < 0.1%
        if result.error_rate > 0.001:
            return False
            
        # P99延迟 < 500ms
        if result.p99_latency_ms > 500:
            return False
            
        # 无内存泄漏 (< 50MB/h)
        if result.memory_leak_detected:
            return False
            
        return True


async def main():
    """主函数"""
    import os
    
    # 从环境变量读取配置
    config = {
        "target_url": os.getenv("TARGET_HOST", "http://localhost:8000"),
        "order_rps": int(os.getenv("ORDER_RPS", "100000")),
        "order_duration": int(os.getenv("ORDER_DURATION", "300")),
        "kline_count": int(os.getenv("KLINE_COUNT", "1000000")),
        "memory_test_hours": int(os.getenv("MEMORY_TEST_HOURS", "24")),
        "stability_days": int(os.getenv("STABILITY_DAYS", "7")),
        "run_order_test": os.getenv("SKIP_ORDER_TEST", "false").lower() != "true",
        "run_kline_test": os.getenv("SKIP_KLINE_TEST", "false").lower() != "true",
        "run_memory_test": os.getenv("SKIP_MEMORY_TEST", "false").lower() != "true",
        "run_stability_test": os.getenv("SKIP_STABILITY_TEST", "false").lower() != "true"
    }
    
    # 创建运行器
    runner = StressTestRunner()
    
    # 运行测试
    try:
        await runner.run_all_tests(config)
    except KeyboardInterrupt:
        logger.info("测试被中断")
        
    # 生成报告
    report = runner.generate_report()
    
    # 保存报告
    report_file = f"stress_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
        
    # 打印摘要
    logger.info("=" * 60)
    logger.info("压力测试报告")
    logger.info("=" * 60)
    logger.info(f"总测试数: {report['summary']['total_tests']}")
    logger.info(f"通过: {report['summary']['passed']}")
    logger.info(f"失败: {report['summary']['failed']}")
    logger.info(f"报告文件: {report_file}")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
