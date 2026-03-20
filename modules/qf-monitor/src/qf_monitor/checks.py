"""检查项模块

提供各种监控检查项，包括账户、持仓、订单、策略状态等。
"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol

import psutil


@dataclass
class CheckResult:
    """检查结果"""

    name: str
    is_healthy: bool
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class HealthCheck(ABC):
    """健康检查基类"""

    @abstractmethod
    async def check(self) -> CheckResult:
        """执行检查

        Returns:
            检查结果
        """
        pass


class AccountCheck(HealthCheck):
    """账户资金检查"""

    def __init__(
        self,
        get_account_func: Optional[callable] = None,
        min_balance: float = 0.0,
        max_drawdown: float = 0.2,
    ):
        """初始化账户检查

        Args:
            get_account_func: 获取账户信息的函数
            min_balance: 最低余额要求
            max_drawdown: 最大回撤限制
        """
        self.get_account_func = get_account_func
        self.min_balance = min_balance
        self.max_drawdown = max_drawdown
        self._balance_history: List[float] = []

    async def check(self) -> CheckResult:
        """检查账户状态"""
        try:
            if self.get_account_func:
                account = await asyncio.to_thread(self.get_account_func)
            else:
                # 模拟账户数据（实际使用时应替换为真实数据获取）
                account = self._get_mock_account()

            balance = account.get("balance", 0.0)
            equity = account.get("equity", balance)
            available = account.get("available", balance)

            # 更新历史记录
            self._balance_history.append(equity)
            if len(self._balance_history) > 100:
                self._balance_history.pop(0)

            # 检查余额
            if balance < self.min_balance:
                return CheckResult(
                    name="AccountCheck",
                    is_healthy=False,
                    message=f"账户余额不足: {balance} < {self.min_balance}",
                    details={
                        "balance": balance,
                        "min_balance": self.min_balance,
                        "severity": "critical",
                    },
                )

            # 检查回撤
            if len(self._balance_history) > 1:
                peak = max(self._balance_history)
                drawdown = (peak - equity) / peak if peak > 0 else 0.0
                if drawdown > self.max_drawdown:
                    return CheckResult(
                        name="AccountCheck",
                        is_healthy=False,
                        message=f"账户回撤超限: {drawdown:.2%} > {self.max_drawdown:.2%}",
                        details={
                            "drawdown": drawdown,
                            "max_drawdown": self.max_drawdown,
                            "peak": peak,
                            "current": equity,
                            "severity": "error",
                        },
                    )

            return CheckResult(
                name="AccountCheck",
                is_healthy=True,
                message="账户状态正常",
                details={
                    "balance": balance,
                    "equity": equity,
                    "available": available,
                    "drawdown": (
                        (max(self._balance_history) - equity) / max(self._balance_history)
                        if self._balance_history and max(self._balance_history) > 0
                        else 0.0
                    ),
                },
            )

        except Exception as e:
            return CheckResult(
                name="AccountCheck",
                is_healthy=False,
                message=f"账户检查异常: {str(e)}",
                details={"error": str(e), "severity": "error"},
            )

    def _get_mock_account(self) -> Dict[str, float]:
        """获取模拟账户数据（用于测试）"""
        return {
            "balance": 100000.0,
            "equity": 100000.0,
            "available": 80000.0,
            "margin": 20000.0,
        }


class PositionCheck(HealthCheck):
    """持仓检查"""

    def __init__(
        self,
        get_positions_func: Optional[callable] = None,
        max_positions: int = 100,
        max_concentration: float = 0.3,
    ):
        """初始化持仓检查

        Args:
            get_positions_func: 获取持仓信息的函数
            max_positions: 最大持仓数量
            max_concentration: 最大持仓集中度
        """
        self.get_positions_func = get_positions_func
        self.max_positions = max_positions
        self.max_concentration = max_concentration

    async def check(self) -> CheckResult:
        """检查持仓状态"""
        try:
            if self.get_positions_func:
                positions = await asyncio.to_thread(self.get_positions_func)
            else:
                positions = []

            total_positions = len(positions)

            # 计算总持仓价值
            total_value = sum(p.get("market_value", 0) for p in positions)
            portfolio_value = sum(p.get("portfolio_value", total_value) for p in positions) or 1.0

            # 检查持仓数量
            if total_positions > self.max_positions:
                return CheckResult(
                    name="PositionCheck",
                    is_healthy=False,
                    message=f"持仓数量超限: {total_positions} > {self.max_positions}",
                    details={
                        "total_positions": total_positions,
                        "max_positions": self.max_positions,
                        "severity": "warning",
                    },
                )

            # 检查持仓集中度
            max_pos_value = max(
                (p.get("market_value", 0) for p in positions),
                default=0.0,
            )
            concentration = max_pos_value / portfolio_value if portfolio_value > 0 else 0.0
            if concentration > self.max_concentration:
                return CheckResult(
                    name="PositionCheck",
                    is_healthy=False,
                    message=f"持仓集中度超限: {concentration:.2%} > {self.max_concentration:.2%}",
                    details={
                        "concentration": concentration,
                        "max_concentration": self.max_concentration,
                        "largest_position": max_pos_value,
                        "severity": "warning",
                    },
                )

            # 检查是否有异常持仓
            abnormal_positions = [
                p for p in positions if p.get("unrealized_pnl", 0) / (p.get("cost", 1) or 1) < -0.1
            ]
            if abnormal_positions:
                return CheckResult(
                    name="PositionCheck",
                    is_healthy=False,
                    message=f"发现 {len(abnormal_positions)} 个异常持仓",
                    details={
                        "abnormal_count": len(abnormal_positions),
                        "positions": [p.get("symbol") for p in abnormal_positions],
                        "severity": "warning",
                    },
                )

            return CheckResult(
                name="PositionCheck",
                is_healthy=True,
                message="持仓状态正常",
                details={
                    "total_positions": total_positions,
                    "total_value": total_value,
                    "concentration": concentration,
                },
            )

        except Exception as e:
            return CheckResult(
                name="PositionCheck",
                is_healthy=False,
                message=f"持仓检查异常: {str(e)}",
                details={"error": str(e), "severity": "error"},
            )


class OrderCheck(HealthCheck):
    """订单检查"""

    def __init__(
        self,
        get_orders_func: Optional[callable] = None,
        max_pending_orders: int = 50,
        max_reject_rate: float = 0.1,
    ):
        """初始化订单检查

        Args:
            get_orders_func: 获取订单信息的函数
            max_pending_orders: 最大挂单数量
            max_reject_rate: 最大拒单率
        """
        self.get_orders_func = get_orders_func
        self.max_pending_orders = max_pending_orders
        self.max_reject_rate = max_reject_rate
        self._order_history: List[Dict[str, Any]] = []

    async def check(self) -> CheckResult:
        """检查订单状态"""
        try:
            if self.get_orders_func:
                orders = await asyncio.to_thread(self.get_orders_func)
            else:
                orders = []

            pending_orders = [o for o in orders if o.get("status") == "pending"]
            rejected_orders = [o for o in orders if o.get("status") == "rejected"]
            filled_orders = [o for o in orders if o.get("status") == "filled"]

            # 检查挂单数量
            if len(pending_orders) > self.max_pending_orders:
                return CheckResult(
                    name="OrderCheck",
                    is_healthy=False,
                    message=f"挂单数量超限: {len(pending_orders)} > {self.max_pending_orders}",
                    details={
                        "pending_count": len(pending_orders),
                        "max_pending": self.max_pending_orders,
                        "severity": "warning",
                    },
                )

            # 检查拒单率
            recent_orders = orders[-100:] if len(orders) > 100 else orders
            total_recent = len(recent_orders)
            if total_recent > 0:
                reject_rate = len(rejected_orders) / total_recent
                if reject_rate > self.max_reject_rate:
                    return CheckResult(
                        name="OrderCheck",
                        is_healthy=False,
                        message=f"拒单率过高: {reject_rate:.2%} > {self.max_reject_rate:.2%}",
                        details={
                            "reject_rate": reject_rate,
                            "max_reject_rate": self.max_reject_rate,
                            "rejected_count": len(rejected_orders),
                            "total_count": total_recent,
                            "severity": "error",
                        },
                    )

            # 检查长时间未成交订单
            long_pending = [
                o for o in pending_orders
                if time.time() - o.get("create_time", 0) > 3600  # 1小时
            ]
            if len(long_pending) > 5:
                return CheckResult(
                    name="OrderCheck",
                    is_healthy=False,
                    message=f"发现 {len(long_pending)} 个长时间未成交订单",
                    details={
                        "long_pending_count": len(long_pending),
                        "severity": "warning",
                    },
                )

            return CheckResult(
                name="OrderCheck",
                is_healthy=True,
                message="订单状态正常",
                details={
                    "pending_count": len(pending_orders),
                    "filled_count": len(filled_orders),
                    "rejected_count": len(rejected_orders),
                },
            )

        except Exception as e:
            return CheckResult(
                name="OrderCheck",
                is_healthy=False,
                message=f"订单检查异常: {str(e)}",
                details={"error": str(e), "severity": "error"},
            )


class StrategyCheck(HealthCheck):
    """策略状态检查"""

    def __init__(
        self,
        get_strategies_func: Optional[callable] = None,
        max_staleness: int = 300,
    ):
        """初始化策略检查

        Args:
            get_strategies_func: 获取策略状态的函数
            max_staleness: 最大允许心跳延迟（秒）
        """
        self.get_strategies_func = get_strategies_func
        self.max_staleness = max_staleness

    async def check(self) -> CheckResult:
        """检查策略状态"""
        try:
            if self.get_strategies_func:
                strategies = await asyncio.to_thread(self.get_strategies_func)
            else:
                strategies = []

            if not strategies:
                return CheckResult(
                    name="StrategyCheck",
                    is_healthy=True,
                    message="无运行中策略",
                    details={"strategies": []},
                )

            issues = []
            now = time.time()

            for strategy in strategies:
                name = strategy.get("name", "unknown")
                status = strategy.get("status", "unknown")
                last_heartbeat = strategy.get("last_heartbeat", 0)
                errors = strategy.get("errors", [])

                # 检查状态
                if status != "running":
                    issues.append({
                        "strategy": name,
                        "issue": f"策略状态异常: {status}",
                        "severity": "error",
                    })
                    continue

                # 检查心跳
                staleness = now - last_heartbeat
                if staleness > self.max_staleness:
                    issues.append({
                        "strategy": name,
                        "issue": f"策略心跳超时: {staleness:.0f}s",
                        "severity": "critical",
                    })
                    continue

                # 检查错误
                if errors:
                    issues.append({
                        "strategy": name,
                        "issue": f"策略错误: {len(errors)} 个",
                        "severity": "error",
                        "errors": errors,
                    })

            if issues:
                critical_count = sum(1 for i in issues if i.get("severity") == "critical")
                return CheckResult(
                    name="StrategyCheck",
                    is_healthy=False,
                    message=f"发现 {len(issues)} 个策略问题（{critical_count} 个严重）",
                    details={
                        "issues": issues,
                        "total_strategies": len(strategies),
                        "severity": "critical" if critical_count > 0 else "error",
                    },
                )

            return CheckResult(
                name="StrategyCheck",
                is_healthy=True,
                message=f"所有 {len(strategies)} 个策略运行正常",
                details={
                    "strategies": [s.get("name") for s in strategies],
                    "total": len(strategies),
                },
            )

        except Exception as e:
            return CheckResult(
                name="StrategyCheck",
                is_healthy=False,
                message=f"策略检查异常: {str(e)}",
                details={"error": str(e), "severity": "error"},
            )


class DataDelayCheck(HealthCheck):
    """数据延迟检查"""

    def __init__(
        self,
        get_data_timestamp_func: Optional[callable] = None,
        max_delay: int = 60,
        symbols: Optional[List[str]] = None,
    ):
        """初始化数据延迟检查

        Args:
            get_data_timestamp_func: 获取数据时间戳的函数
            max_delay: 最大允许延迟（秒）
            symbols: 监控的标的列表
        """
        self.get_data_timestamp_func = get_data_timestamp_func
        self.max_delay = max_delay
        self.symbols = symbols or []

    async def check(self) -> CheckResult:
        """检查数据延迟"""
        try:
            delays = []
            now = time.time()

            if self.get_data_timestamp_func:
                timestamps = await asyncio.to_thread(self.get_data_timestamp_func)
            else:
                # 模拟数据时间戳
                timestamps = {symbol: now - 5 for symbol in self.symbols}

            for symbol, timestamp in timestamps.items():
                delay = now - timestamp
                delays.append({"symbol": symbol, "delay": delay})

            # 找出延迟超限的
            delayed = [d for d in delays if d["delay"] > self.max_delay]

            if delayed:
                max_delay_item = max(delayed, key=lambda x: x["delay"])
                return CheckResult(
                    name="DataDelayCheck",
                    is_healthy=False,
                    message=f"数据延迟超限: {len(delayed)} 个标的，最大 {max_delay_item['delay']:.0f}s",
                    details={
                        "delayed_symbols": [d["symbol"] for d in delayed],
                        "max_delay": max_delay_item["delay"],
                        "threshold": self.max_delay,
                        "severity": "critical" if max_delay_item["delay"] > self.max_delay * 2 else "error",
                    },
                )

            return CheckResult(
                name="DataDelayCheck",
                is_healthy=True,
                message="数据延迟正常",
                details={
                    "max_delay": max((d["delay"] for d in delays), default=0),
                    "avg_delay": sum(d["delay"] for d in delays) / len(delays) if delays else 0,
                },
            )

        except Exception as e:
            return CheckResult(
                name="DataDelayCheck",
                is_healthy=False,
                message=f"数据延迟检查异常: {str(e)}",
                details={"error": str(e), "severity": "error"},
            )


class SystemHealthCheck(HealthCheck):
    """系统资源健康检查"""

    def __init__(
        self,
        cpu_threshold: float = 80.0,
        memory_threshold: float = 80.0,
        disk_threshold: float = 90.0,
        disk_path: str = "/",
    ):
        """初始化系统健康检查

        Args:
            cpu_threshold: CPU 使用率阈值
            memory_threshold: 内存使用率阈值
            disk_threshold: 磁盘使用率阈值
            disk_path: 磁盘路径
        """
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold
        self.disk_threshold = disk_threshold
        self.disk_path = disk_path

    async def check(self) -> CheckResult:
        """检查系统资源"""
        try:
            # CPU 使用率
            cpu_percent = psutil.cpu_percent(interval=0.1)

            # 内存使用率
            memory = psutil.virtual_memory()
            memory_percent = memory.percent

            # 磁盘使用率
            disk = psutil.disk_usage(self.disk_path)
            disk_percent = (disk.used / disk.total) * 100

            issues = []

            if cpu_percent > self.cpu_threshold:
                issues.append(f"CPU 使用率过高: {cpu_percent:.1f}%")

            if memory_percent > self.memory_threshold:
                issues.append(f"内存使用率过高: {memory_percent:.1f}%")

            if disk_percent > self.disk_threshold:
                issues.append(f"磁盘使用率过高: {disk_percent:.1f}%")

            if issues:
                return CheckResult(
                    name="SystemHealthCheck",
                    is_healthy=False,
                    message=f"系统资源异常: {'; '.join(issues)}",
                    details={
                        "cpu_percent": cpu_percent,
                        "memory_percent": memory_percent,
                        "disk_percent": disk_percent,
                        "issues": issues,
                        "severity": "warning",
                    },
                )

            return CheckResult(
                name="SystemHealthCheck",
                is_healthy=True,
                message="系统资源正常",
                details={
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory_percent,
                    "disk_percent": disk_percent,
                    "cpu_count": psutil.cpu_count(),
                    "memory_total": memory.total,
                    "disk_total": disk.total,
                },
            )

        except Exception as e:
            return CheckResult(
                name="SystemHealthCheck",
                is_healthy=False,
                message=f"系统健康检查异常: {str(e)}",
                details={"error": str(e), "severity": "error"},
            )


class DatabaseHealthCheck(HealthCheck):
    """数据库连接健康检查"""

    def __init__(
        self,
        ping_func: Optional[callable] = None,
        timeout: float = 5.0,
    ):
        """初始化数据库健康检查

        Args:
            ping_func: 数据库 ping 函数
            timeout: 超时时间（秒）
        """
        self.ping_func = ping_func
        self.timeout = timeout

    async def check(self) -> CheckResult:
        """检查数据库连接"""
        try:
            if self.ping_func:
                # 带超时执行 ping
                await asyncio.wait_for(
                    asyncio.to_thread(self.ping_func),
                    timeout=self.timeout,
                )
            else:
                # 模拟数据库检查
                await asyncio.sleep(0.01)

            return CheckResult(
                name="DatabaseHealthCheck",
                is_healthy=True,
                message="数据库连接正常",
                details={},
            )

        except asyncio.TimeoutError:
            return CheckResult(
                name="DatabaseHealthCheck",
                is_healthy=False,
                message=f"数据库连接超时 ({self.timeout}s)",
                details={"timeout": self.timeout, "severity": "critical"},
            )
        except Exception as e:
            return CheckResult(
                name="DatabaseHealthCheck",
                is_healthy=False,
                message=f"数据库连接异常: {str(e)}",
                details={"error": str(e), "severity": "critical"},
            )
