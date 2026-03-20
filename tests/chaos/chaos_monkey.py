#!/usr/bin/env python3
"""
QuantForge 混沌测试框架
Chaos Monkey Testing for QuantForge

测试类型:
1. 网络延迟注入 (Network Latency Injection)
2. 服务随机Kill (Service Random Kill)
3. 数据库故障注入 (Database Failure Injection)
4. 时钟偏移测试 (Clock Skew Testing)
5. 资源耗尽测试 (Resource Exhaustion)
"""

import asyncio
import random
import logging
import signal
import sys
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Any, Optional
import subprocess
import json
import os

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [CHAOS] - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ChaosType(Enum):
    """混沌测试类型"""
    NETWORK_LATENCY = "network_latency"
    NETWORK_PARTITION = "network_partition"
    PACKET_LOSS = "packet_loss"
    SERVICE_KILL = "service_kill"
    SERVICE_RESTART = "service_restart"
    CPU_STRESS = "cpu_stress"
    MEMORY_STRESS = "memory_stress"
    DISK_STRESS = "disk_stress"
    CLOCK_SKEW = "clock_skew"
    DATABASE_FAILURE = "database_failure"


@dataclass
class ChaosEvent:
    """混沌事件"""
    chaos_type: ChaosType
    target: str
    duration: int
    intensity: float
    parameters: Dict[str, Any]
    timestamp: datetime


@dataclass
class RecoveryResult:
    """恢复结果"""
    service: str
    recovery_time_ms: float
    success: bool
    error_message: Optional[str] = None


class DockerChaosInjector:
    """Docker容器混沌注入器"""
    
    def __init__(self):
        self.running_chaos: List[ChaosEvent] = []
        
    async def inject_network_latency(
        self, 
        container: str, 
        delay_ms: int = 100, 
        jitter_ms: int = 50,
        duration: int = 60
    ) -> bool:
        """注入网络延迟"""
        logger.info(f"注入网络延迟: {container} - {delay_ms}ms (±{jitter_ms}ms)")
        try:
            cmd = [
                "docker", "exec", container,
                "tc", "qdisc", "add", "dev", "eth0", "root", "netem",
                "delay", f"{delay_ms}ms", f"{jitter_ms}ms"
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            
            await asyncio.sleep(duration)
            
            # 恢复
            self._clear_tc_rules(container)
            return True
        except Exception as e:
            logger.error(f"网络延迟注入失败: {e}")
            return False
    
    async def inject_packet_loss(
        self,
        container: str,
        loss_percent: float = 10.0,
        duration: int = 60
    ) -> bool:
        """注入丢包"""
        logger.info(f"注入丢包: {container} - {loss_percent}%")
        try:
            cmd = [
                "docker", "exec", container,
                "tc", "qdisc", "add", "dev", "eth0", "root", "netem",
                "loss", f"{loss_percent}%"
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            
            await asyncio.sleep(duration)
            
            self._clear_tc_rules(container)
            return True
        except Exception as e:
            logger.error(f"丢包注入失败: {e}")
            return False
    
    async def inject_network_partition(
        self,
        container1: str,
        container2: str,
        duration: int = 60
    ) -> bool:
        """注入网络分区"""
        logger.info(f"注入网络分区: {container1} <-> {container2}")
        try:
            # 获取容器IP
            ip1 = self._get_container_ip(container1)
            ip2 = self._get_container_ip(container2)
            
            # 添加iptables规则阻断通信
            for src, dst in [(ip1, ip2), (ip2, ip1)]:
                cmd = [
                    "docker", "exec", container1,
                    "iptables", "-A", "INPUT", "-s", dst, "-j", "DROP"
                ]
                subprocess.run(cmd, check=True, capture_output=True)
            
            await asyncio.sleep(duration)
            
            # 恢复
            self._clear_iptables_rules(container1)
            return True
        except Exception as e:
            logger.error(f"网络分区注入失败: {e}")
            return False
    
    async def kill_service(self, container: str, signal_type: str = "SIGTERM") -> bool:
        """杀死服务"""
        logger.info(f"杀死服务: {container} - {signal_type}")
        try:
            cmd = ["docker", "kill", f"--signal={signal_type}", container]
            subprocess.run(cmd, check=True, capture_output=True)
            return True
        except Exception as e:
            logger.error(f"服务杀死失败: {e}")
            return False
    
    async def stress_cpu(
        self,
        container: str,
        workers: int = 4,
        duration: int = 60
    ) -> bool:
        """CPU压力测试"""
        logger.info(f"CPU压力测试: {container} - {workers} workers")
        try:
            cmd = [
                "docker", "exec", container,
                "stress-ng", "--cpu", str(workers),
                "--timeout", f"{duration}s",
                "--metrics-brief"
            ]
            subprocess.run(cmd, capture_output=True)
            return True
        except Exception as e:
            logger.error(f"CPU压力测试失败: {e}")
            return False
    
    async def stress_memory(
        self,
        container: str,
        memory_percent: int = 80,
        duration: int = 60
    ) -> bool:
        """内存压力测试"""
        logger.info(f"内存压力测试: {container} - {memory_percent}%")
        try:
            cmd = [
                "docker", "exec", container,
                "stress-ng", "--vm", "4",
                "--vm-bytes", f"{memory_percent}%",
                "--timeout", f"{duration}s"
            ]
            subprocess.run(cmd, capture_output=True)
            return True
        except Exception as e:
            logger.error(f"内存压力测试失败: {e}")
            return False
    
    async def inject_clock_skew(
        self,
        container: str,
        offset_seconds: int = 300,
        duration: int = 60
    ) -> bool:
        """注入时钟偏移"""
        logger.info(f"注入时钟偏移: {container} - {offset_seconds}s")
        try:
            # 在容器内调整时间（需要特权模式）
            cmd = [
                "docker", "exec", "--privileged", container,
                "date", "-s", f"+{offset_seconds} seconds"
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            
            await asyncio.sleep(duration)
            
            # 恢复时间
            cmd = [
                "docker", "exec", "--privileged", container,
                "date", "-s", f"-{offset_seconds} seconds"
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            return True
        except Exception as e:
            logger.error(f"时钟偏移注入失败: {e}")
            return False
    
    async def inject_database_failure(
        self,
        db_container: str = "qf-mysql",
        failure_type: str = "restart",
        duration: int = 30
    ) -> bool:
        """注入数据库故障"""
        logger.info(f"注入数据库故障: {db_container} - {failure_type}")
        try:
            if failure_type == "restart":
                cmd = ["docker", "restart", db_container]
                subprocess.run(cmd, check=True, capture_output=True)
                await asyncio.sleep(duration)
            elif failure_type == "pause":
                cmd = ["docker", "pause", db_container]
                subprocess.run(cmd, check=True, capture_output=True)
                await asyncio.sleep(duration)
                cmd = ["docker", "unpause", db_container]
                subprocess.run(cmd, check=True, capture_output=True)
            return True
        except Exception as e:
            logger.error(f"数据库故障注入失败: {e}")
            return False
    
    def _get_container_ip(self, container: str) -> str:
        """获取容器IP地址"""
        cmd = [
            "docker", "inspect", 
            "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            container
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    
    def _clear_tc_rules(self, container: str):
        """清除TC规则"""
        try:
            cmd = ["docker", "exec", container, "tc", "qdisc", "del", "dev", "eth0", "root"]
            subprocess.run(cmd, capture_output=True)
        except:
            pass
    
    def _clear_iptables_rules(self, container: str):
        """清除iptables规则"""
        try:
            cmd = ["docker", "exec", container, "iptables", "-F"]
            subprocess.run(cmd, capture_output=True)
        except:
            pass


class ChaosMonkey:
    """混沌猴子 - 随机故障注入器"""
    
    def __init__(
        self,
        target_services: List[str],
        interval: int = 300,
        chaos_duration: int = 60
    ):
        self.target_services = target_services
        self.interval = interval
        self.chaos_duration = chaos_duration
        self.injector = DockerChaosInjector()
        self.running = False
        self.chaos_history: List[ChaosEvent] = []
        self.results: List[RecoveryResult] = []
        
    async def start(self):
        """启动混沌测试"""
        logger.info("🐵 混沌猴子已启动")
        self.running = True
        
        while self.running:
            await self._run_chaos_iteration()
            await asyncio.sleep(self.interval)
    
    async def _run_chaos_iteration(self):
        """执行一轮混沌测试"""
        # 随机选择混沌类型
        chaos_type = random.choice(list(ChaosType))
        target = random.choice(self.target_services)
        
        event = ChaosEvent(
            chaos_type=chaos_type,
            target=target,
            duration=self.chaos_duration,
            intensity=random.uniform(0.1, 1.0),
            parameters={},
            timestamp=datetime.now()
        )
        
        logger.info(f"🌀 执行混沌测试: {chaos_type.value} on {target}")
        
        # 记录开始时间
        start_time = datetime.now()
        
        # 执行混沌注入
        success = await self._execute_chaos(event)
        
        # 等待服务恢复
        recovery_result = await self._wait_for_recovery(target, start_time)
        
        self.chaos_history.append(event)
        self.results.append(recovery_result)
        
        if recovery_result.success:
            logger.info(f"✅ 服务已恢复: {target} - {recovery_result.recovery_time_ms:.0f}ms")
        else:
            logger.error(f"❌ 服务恢复失败: {target} - {recovery_result.error_message}")
    
    async def _execute_chaos(self, event: ChaosEvent) -> bool:
        """执行具体的混沌注入"""
        try:
            if event.chaos_type == ChaosType.NETWORK_LATENCY:
                delay = int(50 + event.intensity * 450)  # 50-500ms
                return await self.injector.inject_network_latency(
                    event.target, delay_ms=delay, duration=event.duration
                )
                
            elif event.chaos_type == ChaosType.PACKET_LOSS:
                loss = event.intensity * 20  # 0-20%
                return await self.injector.inject_packet_loss(
                    event.target, loss_percent=loss, duration=event.duration
                )
                
            elif event.chaos_type == ChaosType.SERVICE_KILL:
                signal_type = random.choice(["SIGTERM", "SIGKILL", "SIGHUP"])
                return await self.injector.kill_service(event.target, signal_type)
                
            elif event.chaos_type == ChaosType.CPU_STRESS:
                workers = int(1 + event.intensity * 7)  # 1-8 workers
                return await self.injector.stress_cpu(
                    event.target, workers=workers, duration=event.duration
                )
                
            elif event.chaos_type == ChaosType.MEMORY_STRESS:
                memory = int(50 + event.intensity * 40)  # 50-90%
                return await self.injector.stress_memory(
                    event.target, memory_percent=memory, duration=event.duration
                )
                
            elif event.chaos_type == ChaosType.CLOCK_SKEW:
                offset = int(event.intensity * 600)  # 0-600s
                return await self.injector.inject_clock_skew(
                    event.target, offset_seconds=offset, duration=event.duration
                )
                
            elif event.chaos_type == ChaosType.DATABASE_FAILURE:
                failure_type = random.choice(["restart", "pause"])
                return await self.injector.inject_database_failure(
                    failure_type=failure_type, duration=event.duration
                )
                
            elif event.chaos_type == ChaosType.NETWORK_PARTITION:
                # 需要两个目标
                if len(self.target_services) >= 2:
                    target2 = random.choice([s for s in self.target_services if s != event.target])
                    return await self.injector.inject_network_partition(
                        event.target, target2, duration=event.duration
                    )
                    
            return False
        except Exception as e:
            logger.error(f"混沌注入异常: {e}")
            return False
    
    async def _wait_for_recovery(
        self,
        target: str,
        start_time: datetime,
        timeout: int = 300
    ) -> RecoveryResult:
        """等待服务恢复"""
        check_interval = 5
        elapsed = 0
        
        while elapsed < timeout:
            await asyncio.sleep(check_interval)
            elapsed += check_interval
            
            # 检查服务健康状态
            if await self._check_service_health(target):
                recovery_time = (datetime.now() - start_time).total_seconds() * 1000
                return RecoveryResult(
                    service=target,
                    recovery_time_ms=recovery_time,
                    success=True
                )
        
        return RecoveryResult(
            service=target,
            recovery_time_ms=timeout * 1000,
            success=False,
            error_message="恢复超时"
        )
    
    async def _check_service_health(self, container: str) -> bool:
        """检查服务健康状态"""
        try:
            cmd = ["docker", "inspect", "-f", "{{.State.Health.Status}}", container]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return "healthy" in result.stdout
        except:
            return False
    
    def stop(self):
        """停止混沌测试"""
        self.running = False
        logger.info("🐵 混沌猴子已停止")
    
    def generate_report(self) -> Dict[str, Any]:
        """生成混沌测试报告"""
        total_tests = len(self.chaos_history)
        successful_recoveries = sum(1 for r in self.results if r.success)
        
        avg_recovery_time = (
            sum(r.recovery_time_ms for r in self.results) / len(self.results)
            if self.results else 0
        )
        
        chaos_type_counts = {}
        for event in self.chaos_history:
            chaos_type_counts[event.chaos_type.value] = chaos_type_counts.get(
                event.chaos_type.value, 0
            ) + 1
        
        return {
            "summary": {
                "total_tests": total_tests,
                "successful_recoveries": successful_recoveries,
                "recovery_rate": successful_recoveries / total_tests if total_tests > 0 else 0,
                "avg_recovery_time_ms": avg_recovery_time
            },
            "chaos_distribution": chaos_type_counts,
            "details": [
                {
                    "type": e.chaos_type.value,
                    "target": e.target,
                    "timestamp": e.timestamp.isoformat(),
                    "recovery_time_ms": r.recovery_time_ms,
                    "success": r.success
                }
                for e, r in zip(self.chaos_history, self.results)
            ]
        }


class ChaosScheduler:
    """混沌测试调度器 - 按计划执行混沌测试"""
    
    def __init__(self):
        self.scheduled_tests: List[Dict[str, Any]] = []
        
    def schedule_daily_chaos(
        self,
        hour: int,
        minute: int,
        chaos_config: Dict[str, Any]
    ):
        """安排每日混沌测试"""
        self.scheduled_tests.append({
            "type": "daily",
            "hour": hour,
            "minute": minute,
            "config": chaos_config
        })
    
    def schedule_weekend_chaos(self, chaos_config: Dict[str, Any]):
        """安排周末混沌测试"""
        self.scheduled_tests.append({
            "type": "weekend",
            "config": chaos_config
        })
    
    async def run(self):
        """运行调度器"""
        while True:
            now = datetime.now()
            
            for test in self.scheduled_tests:
                if self._should_run(test, now):
                    await self._execute_scheduled_chaos(test)
            
            await asyncio.sleep(60)  # 每分钟检查一次
    
    def _should_run(self, test: Dict[str, Any], now: datetime) -> bool:
        """检查是否应该执行测试"""
        if test["type"] == "daily":
            return now.hour == test["hour"] and now.minute == test["minute"]
        elif test["type"] == "weekend":
            return now.weekday() >= 5 and now.hour == 2 and now.minute == 0
        return False
    
    async def _execute_scheduled_chaos(self, test: Dict[str, Any]):
        """执行预定的混沌测试"""
        logger.info(f"执行预定混沌测试: {test}")
        monkey = ChaosMonkey(**test["config"])
        
        # 运行一段时间
        asyncio.create_task(monkey.start())
        await asyncio.sleep(test["config"].get("duration", 3600))
        monkey.stop()


async def main():
    """主函数"""
    # 从环境变量获取配置
    target_services = os.getenv(
        "TARGET_SERVICES",
        "qf-data,qf-strategy,qf-execution,qf-risk"
    ).split(",")
    
    interval = int(os.getenv("CHAOS_INTERVAL", "300"))
    duration = int(os.getenv("CHAOS_DURATION", "60"))
    run_duration = int(os.getenv("RUN_DURATION", "3600"))
    
    logger.info("=" * 60)
    logger.info("QuantForge 混沌测试框架")
    logger.info("=" * 60)
    logger.info(f"目标服务: {target_services}")
    logger.info(f"混沌间隔: {interval}s")
    logger.info(f"混沌持续时间: {duration}s")
    logger.info(f"总运行时间: {run_duration}s")
    
    # 创建混沌猴子
    monkey = ChaosMonkey(
        target_services=target_services,
        interval=interval,
        chaos_duration=duration
    )
    
    # 设置信号处理
    def signal_handler(sig, frame):
        logger.info("收到停止信号")
        monkey.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 启动混沌测试
    task = asyncio.create_task(monkey.start())
    
    # 运行指定时间
    await asyncio.sleep(run_duration)
    
    # 停止并生成报告
    monkey.stop()
    await task
    
    report = monkey.generate_report()
    
    # 保存报告
    report_file = f"chaos_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info("=" * 60)
    logger.info("混沌测试完成")
    logger.info(f"报告已保存: {report_file}")
    logger.info(f"总测试数: {report['summary']['total_tests']}")
    logger.info(f"恢复成功率: {report['summary']['recovery_rate']:.2%}")
    logger.info(f"平均恢复时间: {report['summary']['avg_recovery_time_ms']:.0f}ms")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
