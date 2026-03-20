"""额外的通知器测试和边界情况测试"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import responses

from qf_monitor import (
    Alert,
    AlertLevel,
    AlertManager,
    CheckResult,
    Monitor,
    MonitorConfig,
)
from qf_monitor.checks import DatabaseHealthCheck, SystemHealthCheck
from qf_monitor.notifiers import DingTalkNotifier, EmailNotifier, WechatWorkNotifier


# ==================== Test DatabaseHealthCheck ====================


class TestDatabaseHealthCheck:
    """数据库健康检查测试"""

    @pytest.mark.asyncio
    async def test_database_healthy(self):
        """测试数据库连接正常"""
        mock_ping = Mock(return_value=True)
        check = DatabaseHealthCheck(ping_func=mock_ping)
        result = await check.check()

        assert result.is_healthy is True
        assert "正常" in result.message

    @pytest.mark.asyncio
    async def test_database_connection_error(self):
        """测试数据库连接异常"""
        mock_ping = Mock(side_effect=Exception("连接失败"))
        check = DatabaseHealthCheck(ping_func=mock_ping)
        result = await check.check()

        assert result.is_healthy is False
        assert "连接异常" in result.message
        assert result.details["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_database_timeout(self):
        """测试数据库连接超时"""
        # 使用一个会超时的函数
        def slow_ping():
            import time
            time.sleep(10)

        check = DatabaseHealthCheck(ping_func=slow_ping, timeout=0.01)
        result = await check.check()

        assert result.is_healthy is False
        assert "超时" in result.message


# ==================== Test SystemHealthCheck ====================


class TestSystemHealthCheck:
    """系统健康检查测试"""

    @pytest.mark.asyncio
    async def test_system_healthy(self):
        """测试系统资源正常"""
        check = SystemHealthCheck(
            cpu_threshold=99.0,
            memory_threshold=99.0,
            disk_threshold=99.0,
        )
        result = await check.check()

        assert result.is_healthy is True
        assert "正常" in result.message
        assert "cpu_percent" in result.details

    @pytest.mark.asyncio
    @patch("psutil.cpu_percent", return_value=85.0)
    @patch("psutil.virtual_memory")
    @patch("psutil.disk_usage")
    async def test_high_cpu(self, mock_disk, mock_memory, mock_cpu):
        """测试CPU使用率过高"""
        mock_mem = MagicMock()
        mock_mem.percent = 50.0
        mock_memory.return_value = mock_mem

        mock_disk_ret = MagicMock()
        mock_disk_ret.used = 50
        mock_disk_ret.total = 100
        mock_disk.return_value = mock_disk_ret

        check = SystemHealthCheck(cpu_threshold=80.0)
        result = await check.check()

        assert result.is_healthy is False
        assert "CPU" in result.message


# ==================== Test AlertManager Additional ====================


class TestAlertManagerAdditional:
    """报警管理器额外测试"""

    @pytest.mark.asyncio
    async def test_notifier_failure(self):
        """测试通知器发送失败"""
        manager = AlertManager()
        failing_notifier = MagicMock()
        failing_notifier.send = AsyncMock(side_effect=Exception("发送失败"))

        manager.add_notifier("failing", failing_notifier)

        alert = Alert(
            level=AlertLevel.ERROR,
            title="测试",
            message="测试消息",
        )

        results = await manager.send_alert(alert)
        assert results["failing"] is False

    @pytest.mark.asyncio
    async def test_notifier_timeout(self):
        """测试通知器超时"""
        manager = AlertManager()
        slow_notifier = MagicMock()

        async def slow_send(*args, **kwargs):
            await asyncio.sleep(20)
            return True

        slow_notifier.send = slow_send
        manager.add_notifier("slow", slow_notifier)

        alert = Alert(
            level=AlertLevel.ERROR,
            title="测试",
            message="测试消息",
        )

        results = await manager.send_alert(alert)
        assert results["slow"] is False  # 应该超时返回 False

    def test_has_notifiers(self):
        """测试 has_notifiers 方法"""
        manager = AlertManager()
        assert manager.has_notifiers() is False

        manager.add_notifier("test", MagicMock())
        assert manager.has_notifiers() is True


# ==================== Test Notifiers with Real HTTP ====================


class TestWechatWorkNotifierAdditional:
    """企业微信通知器额外测试"""

    @responses.activate
    def test_send_text(self):
        """测试发送纯文本消息"""
        responses.add(
            responses.POST,
            "https://qyapi.weixin.qq.com/cgi-bin/webhook/send",
            json={"errcode": 0, "errmsg": "ok"},
            status=200,
        )

        notifier = WechatWorkNotifier(webhook_key="test_key")
        result = notifier.send_text("测试消息")
        assert result is True

    @responses.activate
    def test_send_text_failure(self):
        """测试发送文本消息失败"""
        responses.add(
            responses.POST,
            "https://qyapi.weixin.qq.com/cgi-bin/webhook/send",
            json={"errcode": 40001, "errmsg": "invalid credential"},
            status=200,
        )

        notifier = WechatWorkNotifier(webhook_key="test_key")
        result = notifier.send_text("测试消息")
        assert result is False


class TestDingTalkNotifierAdditional:
    """钉钉通知器额外测试"""

    @responses.activate
    def test_send_text(self):
        """测试发送纯文本消息"""
        responses.add(
            responses.POST,
            "https://oapi.dingtalk.com/robot/send",
            json={"errcode": 0, "errmsg": "ok"},
            status=200,
        )

        notifier = DingTalkNotifier(access_token="test_token")
        result = notifier.send_text("测试消息")
        assert result is True

    @responses.activate
    def test_send_text_failure(self):
        """测试发送文本消息失败"""
        responses.add(
            responses.POST,
            "https://oapi.dingtalk.com/robot/send",
            json={"errcode": 400001, "errmsg": "invalid timestamp"},
            status=200,
        )

        notifier = DingTalkNotifier(access_token="test_token")
        result = notifier.send_text("测试消息")
        assert result is False

    def test_generate_sign_no_secret(self):
        """测试没有密钥时的签名生成"""
        notifier = DingTalkNotifier(access_token="test_token", secret=None)
        timestamp, sign = notifier._generate_sign()
        assert timestamp is not None
        assert sign == ""  # 没有密钥时签名为空


# ==================== Test Monitor Additional ====================


class TestMonitorAdditional:
    """监控器额外测试"""

    @pytest.mark.asyncio
    async def test_add_remove_notifier(self):
        """测试添加和移除通知器"""
        monitor = Monitor()
        mock_notifier = MagicMock()

        monitor.add_notifier("test", mock_notifier)
        assert "test" in monitor._alert_manager.get_notifier_names()

        removed = monitor.remove_notifier("test")
        assert removed is True
        assert "test" not in monitor._alert_manager.get_notifier_names()

    def test_remove_nonexistent_notifier(self):
        """测试移除不存在的通知器"""
        monitor = Monitor()
        removed = monitor.remove_notifier("nonexistent")
        assert removed is False

    @pytest.mark.asyncio
    async def test_determine_alert_level(self):
        """测试报警级别判断"""
        monitor = Monitor()

        # 测试 critical 级别
        result = CheckResult(
            name="Test",
            is_healthy=False,
            message="测试",
            details={"severity": "critical"},
        )
        level = monitor._determine_alert_level(result)
        assert level == AlertLevel.CRITICAL

        # 测试 error 级别
        result = CheckResult(
            name="Test",
            is_healthy=False,
            message="测试",
            details={"severity": "error"},
        )
        level = monitor._determine_alert_level(result)
        assert level == AlertLevel.ERROR

        # 测试 warning 级别
        result = CheckResult(
            name="Test",
            is_healthy=False,
            message="测试",
            details={"severity": "warning"},
        )
        level = monitor._determine_alert_level(result)
        assert level == AlertLevel.WARNING

        # 测试健康状态
        result = CheckResult(
            name="Test",
            is_healthy=True,
            message="正常",
        )
        level = monitor._determine_alert_level(result)
        assert level == AlertLevel.INFO


# ==================== Test Alert Methods ====================


class TestAlertMethods:
    """报警类方法测试"""

    def test_alert_level_priority_comparison(self):
        """测试报警级别优先级比较"""
        assert AlertLevel.CRITICAL.priority > AlertLevel.ERROR.priority
        assert AlertLevel.ERROR.priority > AlertLevel.WARNING.priority
        assert AlertLevel.WARNING.priority > AlertLevel.INFO.priority
        assert AlertLevel.INFO.priority > AlertLevel.DEBUG.priority

    def test_alert_with_empty_details(self):
        """测试空详情的报警格式化"""
        alert = Alert(
            level=AlertLevel.INFO,
            title="测试",
            message="消息",
            details={},
        )
        formatted = alert.format_message()
        assert "测试" in formatted
        assert "消息" in formatted


# ==================== Test Callbacks ====================


class TestCallbacks:
    """回调功能测试"""

    def test_callback_with_exception(self):
        """测试回调抛出异常"""
        monitor = Monitor()

        def bad_callback(result):
            raise ValueError("回调错误")

        monitor.add_callback("check_passed", bad_callback)

        # 创建一个通过的检查结果
        result = CheckResult(name="Test", is_healthy=True, message="OK")

        # 不应该抛出异常
        monitor._trigger_callbacks("check_passed", result)

    @pytest.mark.asyncio
    async def test_remove_nonexistent_callback(self):
        """测试移除不存在的回调"""
        monitor = Monitor()
        callback = lambda x: None

        # 事件不存在
        removed = monitor.remove_callback("nonexistent", callback)
        assert removed is False

        # 回调不存在于事件中
        monitor.add_callback("event", lambda x: None)
        removed = monitor.remove_callback("event", callback)
        assert removed is False
