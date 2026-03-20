"""qf-monitor 测试模块

测试监控、检查项、报警系统的各项功能。
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from qf_monitor import (
    AccountCheck,
    Alert,
    AlertLevel,
    AlertManager,
    CheckResult,
    DataDelayCheck,
    HealthCheck,
    Monitor,
    MonitorConfig,
    OrderCheck,
    PositionCheck,
    StrategyCheck,
)
from qf_monitor.notifiers import DingTalkNotifier, EmailNotifier, WechatWorkNotifier


# ==================== Test Fixtures ====================


@pytest.fixture
def monitor_config():
    """监控配置 fixture"""
    return MonitorConfig(
        check_interval=1,
        data_delay_threshold=60,
        cpu_threshold=80.0,
        memory_threshold=80.0,
        disk_threshold=90.0,
        alert_cooldown=1,
    )


@pytest.fixture
def monitor(monitor_config):
    """Monitor 实例 fixture"""
    return Monitor(monitor_config)


@pytest.fixture
def alert_manager():
    """AlertManager 实例 fixture"""
    return AlertManager()


@pytest.fixture
def mock_notifier():
    """模拟通知器 fixture"""
    notifier = MagicMock()
    notifier.send = AsyncMock(return_value=True)
    return notifier


# ==================== Test MonitorConfig ====================


class TestMonitorConfig:
    """测试监控配置"""

    def test_default_config(self):
        """测试默认配置"""
        config = MonitorConfig()
        assert config.check_interval == 30
        assert config.data_delay_threshold == 60
        assert config.cpu_threshold == 80.0
        assert config.alert_cooldown == 300

    def test_custom_config(self):
        """测试自定义配置"""
        config = MonitorConfig(
            check_interval=60,
            data_delay_threshold=120,
            cpu_threshold=90.0,
        )
        assert config.check_interval == 60
        assert config.data_delay_threshold == 120
        assert config.cpu_threshold == 90.0


# ==================== Test CheckResult ====================


class TestCheckResult:
    """测试结果类测试"""

    def test_healthy_result(self):
        """测试健康结果"""
        result = CheckResult(
            name="TestCheck",
            is_healthy=True,
            message="一切正常",
            details={"key": "value"},
        )
        assert result.is_healthy is True
        assert result.name == "TestCheck"
        assert result.message == "一切正常"
        assert result.details["key"] == "value"

    def test_unhealthy_result(self):
        """测试非健康结果"""
        result = CheckResult(
            name="TestCheck",
            is_healthy=False,
            message="发生错误",
            details={"severity": "critical"},
        )
        assert result.is_healthy is False
        assert result.details["severity"] == "critical"


# ==================== Test Alert ====================


class TestAlert:
    """报警类测试"""

    def test_alert_creation(self):
        """测试报警创建"""
        alert = Alert(
            level=AlertLevel.ERROR,
            title="测试报警",
            message="测试消息",
            details={"key": "value"},
        )
        assert alert.level == AlertLevel.ERROR
        assert alert.title == "测试报警"
        assert alert.message == "测试消息"
        assert "key" in alert.details

    def test_alert_to_dict(self):
        """测试报警转字典"""
        alert = Alert(
            level=AlertLevel.WARNING,
            title="测试",
            message="消息",
        )
        d = alert.to_dict()
        assert d["level"] == "warning"
        assert d["title"] == "测试"
        assert "alert_id" in d
        assert "timestamp" in d

    def test_alert_format_message(self):
        """测试报警格式化"""
        alert = Alert(
            level=AlertLevel.CRITICAL,
            title="严重错误",
            message="系统崩溃",
            details={"error_code": 500},
        )
        formatted = alert.format_message()
        assert "CRITICAL" in formatted
        assert "严重错误" in formatted
        assert "error_code" in formatted


# ==================== Test AlertLevel ====================


class TestAlertLevel:
    """报警级别测试"""

    def test_priority_values(self):
        """测试优先级数值"""
        assert AlertLevel.DEBUG.priority == 0
        assert AlertLevel.INFO.priority == 1
        assert AlertLevel.WARNING.priority == 2
        assert AlertLevel.ERROR.priority == 3
        assert AlertLevel.CRITICAL.priority == 4

    def test_priority_ordering(self):
        """测试优先级排序"""
        levels = [AlertLevel.ERROR, AlertLevel.DEBUG, AlertLevel.CRITICAL, AlertLevel.WARNING]
        sorted_levels = sorted(levels, key=lambda x: x.priority)
        assert sorted_levels == [AlertLevel.DEBUG, AlertLevel.WARNING, AlertLevel.ERROR, AlertLevel.CRITICAL]


# ==================== Test AlertManager ====================


class TestAlertManager:
    """报警管理器测试"""

    @pytest.mark.asyncio
    async def test_add_remove_notifier(self, alert_manager, mock_notifier):
        """测试添加和移除通知器"""
        alert_manager.add_notifier("test", mock_notifier)
        assert "test" in alert_manager.get_notifier_names()

        removed = alert_manager.remove_notifier("test")
        assert removed is True
        assert "test" not in alert_manager.get_notifier_names()

    def test_remove_nonexistent_notifier(self, alert_manager):
        """测试移除不存在的通知器"""
        removed = alert_manager.remove_notifier("nonexistent")
        assert removed is False

    @pytest.mark.asyncio
    async def test_send_alert(self, alert_manager, mock_notifier):
        """测试发送报警"""
        alert_manager.add_notifier("test", mock_notifier)

        alert = Alert(
            level=AlertLevel.ERROR,
            title="测试报警",
            message="测试消息",
        )

        results = await alert_manager.send_alert(alert)
        assert results["test"] is True
        mock_notifier.send.assert_called_once_with(alert)

    @pytest.mark.asyncio
    async def test_send_alert_filtered_by_level(self, alert_manager, mock_notifier):
        """测试按级别过滤报警"""
        alert_manager.add_notifier("test", mock_notifier)
        alert_manager.set_min_level(AlertLevel.WARNING)

        # DEBUG 级别应该被过滤
        debug_alert = Alert(
            level=AlertLevel.DEBUG,
            title="调试",
            message="调试信息",
        )
        results = await alert_manager.send_alert(debug_alert)
        assert results == {}  # 被过滤，没有发送
        mock_notifier.send.assert_not_called()

        # ERROR 级别应该发送
        error_alert = Alert(
            level=AlertLevel.ERROR,
            title="错误",
            message="错误信息",
        )
        results = await alert_manager.send_alert(error_alert)
        assert "test" in results

    def test_get_history(self, alert_manager):
        """测试获取报警历史"""
        # 发送一些报警
        for i in range(5):
            alert = Alert(
                level=AlertLevel.WARNING if i % 2 == 0 else AlertLevel.ERROR,
                title=f"报警{i}",
                message=f"消息{i}",
            )
            asyncio.run(alert_manager.send_alert(alert))

        history = alert_manager.get_history(limit=3)
        assert len(history) == 3

        # 按级别过滤
        warning_history = alert_manager.get_history(level=AlertLevel.WARNING)
        assert all(a.level == AlertLevel.WARNING for a in warning_history)

    def test_clear_history(self, alert_manager):
        """测试清空历史"""
        alert = Alert(
            level=AlertLevel.INFO,
            title="测试",
            message="消息",
        )
        asyncio.run(alert_manager.send_alert(alert))

        assert len(alert_manager.get_history()) > 0
        alert_manager.clear_history()
        assert len(alert_manager.get_history()) == 0


# ==================== Test Monitor ====================


class TestMonitor:
    """监控核心测试"""

    def test_monitor_init(self, monitor, monitor_config):
        """测试监控器初始化"""
        assert monitor.config == monitor_config
        assert monitor.is_running is False
        assert len(monitor.registered_checks) == 0

    def test_register_unregister_check(self, monitor):
        """测试注册和注销检查项"""
        check = AccountCheck()
        monitor.register_check(check)
        assert "AccountCheck" in monitor.registered_checks

        removed = monitor.unregister_check(AccountCheck)
        assert removed is True
        assert "AccountCheck" not in monitor.registered_checks

    def test_unregister_nonexistent_check(self, monitor):
        """测试注销不存在的检查项"""
        removed = monitor.unregister_check(AccountCheck)
        assert removed is False

    def test_add_remove_callback(self, monitor):
        """测试添加和移除回调"""
        callback = MagicMock()
        monitor.add_callback("check_passed", callback)

        # 检查回调已添加（通过执行检查触发）
        result = CheckResult(name="Test", is_healthy=True, message="OK")
        monitor._trigger_callbacks("check_passed", result)
        callback.assert_called_once_with(result)

        # 移除回调
        removed = monitor.remove_callback("check_passed", callback)
        assert removed is True

    @pytest.mark.asyncio
    async def test_check_once_with_passing_check(self, monitor):
        """测试检查通过的情况"""
        check = MagicMock(spec=HealthCheck)
        check.check = AsyncMock(return_value=CheckResult(
            name="TestCheck",
            is_healthy=True,
            message="正常",
        ))

        monitor.register_check(check)
        results = await monitor.check_once()

        assert len(results) == 1
        assert results[0].is_healthy is True
        assert monitor.get_stats()["checks_passed"] == 1

    @pytest.mark.asyncio
    async def test_check_once_with_failing_check(self, monitor):
        """测试检查失败的情况"""
        check = MagicMock(spec=HealthCheck)
        check.check = AsyncMock(return_value=CheckResult(
            name="TestCheck",
            is_healthy=False,
            message="错误",
            details={"severity": "error"},
        ))

        monitor.register_check(check)
        results = await monitor.check_once()

        assert len(results) == 1
        assert results[0].is_healthy is False
        assert monitor.get_stats()["checks_failed"] == 1

    @pytest.mark.asyncio
    async def test_check_once_with_exception(self, monitor):
        """测试检查抛出异常的情况"""
        check = MagicMock(spec=HealthCheck)
        check.check = AsyncMock(side_effect=Exception("检查错误"))
        check.__class__.__name__ = "FaultyCheck"

        monitor.register_check(check)
        results = await monitor.check_once()

        assert len(results) == 1
        assert results[0].is_healthy is False
        assert "检查执行异常" in results[0].message

    @pytest.mark.asyncio
    async def test_check_status(self, monitor):
        """测试获取监控状态"""
        status = await monitor.check_status()
        assert "running" in status
        assert "checks" in status
        assert "stats" in status

    @pytest.mark.asyncio
    async def test_start_stop(self, monitor):
        """测试启动和停止"""
        assert monitor.is_running is False

        # 在后台启动监控
        task = asyncio.create_task(monitor.start())
        await asyncio.sleep(0.1)  # 给一点时间启动

        assert monitor.is_running is True

        # 停止
        monitor.stop()
        # 等待任务完成
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except asyncio.TimeoutError:
            pass

        assert monitor.is_running is False

    @pytest.mark.asyncio
    async def test_alert_cooldown(self, monitor):
        """测试报警冷却"""
        # 添加模拟通知器
        mock_notifier = MagicMock()
        mock_notifier.send = AsyncMock(return_value=True)
        monitor.add_notifier("test", mock_notifier)

        # 注册失败的检查项
        check = MagicMock(spec=HealthCheck)
        check.check = AsyncMock(return_value=CheckResult(
            name="TestCheck",
            is_healthy=False,
            message="错误",
            details={"severity": "error"},
        ))
        monitor.register_check(check)

        # 第一次检查，应该发送报警
        await monitor.check_once()
        assert mock_notifier.send.call_count == 1

        # 第二次检查，冷却期内，不应该发送
        await monitor.check_once()
        assert mock_notifier.send.call_count == 1  # 没有增加


# ==================== Test AccountCheck ====================


class TestAccountCheck:
    """账户检查测试"""

    @pytest.mark.asyncio
    async def test_healthy_account(self):
        """测试健康账户"""
        get_account = Mock(return_value={
            "balance": 100000,
            "equity": 100000,
            "available": 80000,
        })

        check = AccountCheck(get_account_func=get_account, min_balance=50000)
        result = await check.check()

        assert result.is_healthy is True
        assert "正常" in result.message

    @pytest.mark.asyncio
    async def test_low_balance(self):
        """测试余额不足"""
        get_account = Mock(return_value={
            "balance": 1000,
            "equity": 1000,
        })

        check = AccountCheck(get_account_func=get_account, min_balance=5000)
        result = await check.check()

        assert result.is_healthy is False
        assert "余额不足" in result.message
        assert result.details["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_drawdown_exceeded(self):
        """测试回撤超限"""
        get_account = Mock(return_value={
            "balance": 100000,
            "equity": 70000,
        })

        check = AccountCheck(get_account_func=get_account, max_drawdown=0.2)
        # 模拟历史高水位
        check._balance_history = [100000, 100000, 100000]

        result = await check.check()

        assert result.is_healthy is False
        assert "回撤" in result.message


# ==================== Test PositionCheck ====================


class TestPositionCheck:
    """持仓检查测试"""

    @pytest.mark.asyncio
    async def test_no_positions(self):
        """测试无持仓"""
        check = PositionCheck(get_positions_func=lambda: [])
        result = await check.check()

        assert result.is_healthy is True
        assert result.details["total_positions"] == 0

    @pytest.mark.asyncio
    async def test_healthy_positions(self):
        """测试健康持仓"""
        positions = [
            {"symbol": "AAPL", "market_value": 5000, "portfolio_value": 100000},
            {"symbol": "GOOGL", "market_value": 5000, "portfolio_value": 100000},
        ]
        check = PositionCheck(get_positions_func=lambda: positions)
        result = await check.check()

        assert result.is_healthy is True
        assert result.details["total_positions"] == 2

    @pytest.mark.asyncio
    async def test_too_many_positions(self):
        """测试持仓数量超限"""
        positions = [{"symbol": f"STOCK{i}", "market_value": 100} for i in range(10)]
        check = PositionCheck(get_positions_func=lambda: positions, max_positions=5)
        result = await check.check()

        assert result.is_healthy is False
        assert "数量超限" in result.message

    @pytest.mark.asyncio
    async def test_high_concentration(self):
        """测试持仓集中度过高"""
        positions = [
            {"symbol": "AAPL", "market_value": 80000, "portfolio_value": 100000},
            {"symbol": "GOOGL", "market_value": 20000, "portfolio_value": 100000},
        ]
        check = PositionCheck(get_positions_func=lambda: positions, max_concentration=0.5)
        result = await check.check()

        assert result.is_healthy is False
        assert "集中度" in result.message

    @pytest.mark.asyncio
    async def test_abnormal_positions(self):
        """测试异常持仓"""
        positions = [
            {"symbol": "LOSER", "market_value": 80, "cost": 100, "unrealized_pnl": -20, "portfolio_value": 100000},
        ]
        check = PositionCheck(get_positions_func=lambda: positions)
        result = await check.check()

        assert result.is_healthy is False
        assert "异常持仓" in result.message


# ==================== Test OrderCheck ====================


class TestOrderCheck:
    """订单检查测试"""

    @pytest.mark.asyncio
    async def test_no_orders(self):
        """测试无订单"""
        check = OrderCheck(get_orders_func=lambda: [])
        result = await check.check()

        assert result.is_healthy is True

    @pytest.mark.asyncio
    async def test_too_many_pending_orders(self):
        """测试挂单过多"""
        orders = [{"status": "pending"} for _ in range(20)]
        check = OrderCheck(get_orders_func=lambda: orders, max_pending_orders=10)
        result = await check.check()

        assert result.is_healthy is False
        assert "挂单" in result.message

    @pytest.mark.asyncio
    async def test_high_reject_rate(self):
        """测试拒单率过高"""
        orders = [{"status": "rejected"} for _ in range(20)]
        orders += [{"status": "filled"} for _ in range(80)]
        check = OrderCheck(get_orders_func=lambda: orders, max_reject_rate=0.1)
        result = await check.check()

        assert result.is_healthy is False
        assert "拒单率" in result.message

    @pytest.mark.asyncio
    async def test_long_pending_orders(self):
        """测试长时间未成交订单"""
        import time
        orders = [
            {"status": "pending", "create_time": time.time() - 7200} for _ in range(10)
        ]
        check = OrderCheck(get_orders_func=lambda: orders)
        result = await check.check()

        assert result.is_healthy is False
        assert "长时间未成交" in result.message


# ==================== Test StrategyCheck ====================


class TestStrategyCheck:
    """策略检查测试"""

    @pytest.mark.asyncio
    async def test_no_strategies(self):
        """测试无策略"""
        check = StrategyCheck(get_strategies_func=lambda: [])
        result = await check.check()

        assert result.is_healthy is True
        assert "无运行中策略" in result.message

    @pytest.mark.asyncio
    async def test_healthy_strategies(self):
        """测试健康策略"""
        import time
        strategies = [
            {"name": "Strategy1", "status": "running", "last_heartbeat": time.time(), "errors": []},
            {"name": "Strategy2", "status": "running", "last_heartbeat": time.time(), "errors": []},
        ]
        check = StrategyCheck(get_strategies_func=lambda: strategies)
        result = await check.check()

        assert result.is_healthy is True
        assert "运行正常" in result.message

    @pytest.mark.asyncio
    async def test_stopped_strategy(self):
        """测试停止的策略"""
        strategies = [{"name": "BadStrategy", "status": "stopped", "last_heartbeat": 0, "errors": []}]
        check = StrategyCheck(get_strategies_func=lambda: strategies)
        result = await check.check()

        assert result.is_healthy is False
        # 检查详情中是否有策略状态异常的信息
        assert any("策略状态异常" in issue.get("issue", "") for issue in result.details.get("issues", []))

    @pytest.mark.asyncio
    async def test_heartbeat_timeout(self):
        """测试心跳超时"""
        import time
        strategies = [
            {"name": "DeadStrategy", "status": "running", "last_heartbeat": time.time() - 1000, "errors": []}
        ]
        check = StrategyCheck(get_strategies_func=lambda: strategies, max_staleness=300)
        result = await check.check()

        assert result.is_healthy is False
        # 检查详情中是否有心跳超时的信息
        assert any("心跳超时" in issue.get("issue", "") for issue in result.details.get("issues", []))
        assert result.details["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_strategy_with_errors(self):
        """测试有错误的策略"""
        import time
        strategies = [
            {
                "name": "ErrorStrategy",
                "status": "running",
                "last_heartbeat": time.time(),
                "errors": ["Error1", "Error2"],
            }
        ]
        check = StrategyCheck(get_strategies_func=lambda: strategies)
        result = await check.check()

        assert result.is_healthy is False
        # 检查详情中是否有策略错误的信息
        assert any("策略错误" in issue.get("issue", "") for issue in result.details.get("issues", []))


# ==================== Test DataDelayCheck ====================


class TestDataDelayCheck:
    """数据延迟检查测试"""

    @pytest.mark.asyncio
    async def test_no_delay(self):
        """测试无延迟"""
        import time
        timestamps = {"AAPL": time.time(), "GOOGL": time.time()}
        check = DataDelayCheck(get_data_timestamp_func=lambda: timestamps)
        result = await check.check()

        assert result.is_healthy is True
        assert "正常" in result.message

    @pytest.mark.asyncio
    async def test_delayed_data(self):
        """测试数据延迟"""
        import time
        timestamps = {"AAPL": time.time() - 120, "GOOGL": time.time() - 5}
        check = DataDelayCheck(get_data_timestamp_func=lambda: timestamps, max_delay=60)
        result = await check.check()

        assert result.is_healthy is False
        assert "延迟" in result.message
        assert "AAPL" in result.details["delayed_symbols"]


# ==================== Test Notifiers ====================


class TestEmailNotifier:
    """邮件通知器测试"""

    @pytest.mark.asyncio
    @patch("smtplib.SMTP")
    async def test_send_email(self, mock_smtp):
        """测试发送邮件"""
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server

        notifier = EmailNotifier(
            smtp_host="smtp.example.com",
            smtp_port=587,
            username="test@example.com",
            password="password",
            from_addr="from@example.com",
            to_addrs=["to@example.com"],
        )

        alert = Alert(
            level=AlertLevel.ERROR,
            title="测试报警",
            message="测试消息",
        )

        result = await notifier.send(alert)
        assert result is True
        mock_server.sendmail.assert_called_once()


class TestWechatWorkNotifier:
    """企业微信通知器测试"""

    @pytest.mark.asyncio
    @patch("requests.post")
    async def test_send_wechat(self, mock_post):
        """测试发送企业微信消息"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"errcode": 0}
        mock_post.return_value = mock_response

        notifier = WechatWorkNotifier(webhook_key="test_key")

        alert = Alert(
            level=AlertLevel.WARNING,
            title="测试报警",
            message="测试消息",
        )

        result = await notifier.send(alert)
        assert result is True
        mock_post.assert_called_once()


class TestDingTalkNotifier:
    """钉钉通知器测试"""

    @pytest.mark.asyncio
    @patch("requests.post")
    async def test_send_dingtalk(self, mock_post):
        """测试发送钉钉消息"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"errcode": 0}
        mock_post.return_value = mock_response

        notifier = DingTalkNotifier(access_token="test_token")

        alert = Alert(
            level=AlertLevel.CRITICAL,
            title="测试报警",
            message="测试消息",
        )

        result = await notifier.send(alert)
        assert result is True
        mock_post.assert_called_once()

    def test_generate_sign(self):
        """测试签名生成"""
        notifier = DingTalkNotifier(
            access_token="test",
            secret="test_secret",
        )
        timestamp, sign = notifier._generate_sign()
        assert timestamp is not None
        assert sign is not None


# ==================== Test System Integration ====================


class TestSystemIntegration:
    """系统集成测试"""

    @pytest.mark.asyncio
    async def test_full_monitoring_workflow(self):
        """测试完整监控流程"""
        # 创建监控器
        config = MonitorConfig(check_interval=1, alert_cooldown=1)
        monitor = Monitor(config)

        # 添加检查项
        monitor.register_check(AccountCheck())
        monitor.register_check(PositionCheck())

        # 添加模拟通知器
        mock_notifier = MagicMock()
        mock_notifier.send = AsyncMock(return_value=True)
        monitor.add_notifier("mock", mock_notifier)

        # 执行检查
        results = await monitor.check_once()
        assert len(results) == 2

        # 验证状态
        stats = monitor.get_stats()
        assert stats["checks_total"] == 2

    @pytest.mark.asyncio
    async def test_callback_invocation(self):
        """测试回调调用"""
        monitor = Monitor()

        callback_results = []
        def callback(result):
            callback_results.append(result)

        monitor.add_callback("check_passed", callback)

        # 注册通过的检查项
        check = MagicMock(spec=HealthCheck)
        check.check = AsyncMock(return_value=CheckResult(
            name="Test",
            is_healthy=True,
            message="OK",
        ))
        monitor.register_check(check)

        await monitor.check_once()

        assert len(callback_results) == 1
        assert callback_results[0].is_healthy is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
