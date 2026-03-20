"""企业微信通知器

通过企业微信机器人发送报警。
"""

import asyncio
from typing import Optional

import requests
import structlog

from ..alerts import Alert, AlertLevel, Notifier

logger = structlog.get_logger()


class WechatWorkNotifier:
    """企业微信机器人通知器"""

    WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"

    def __init__(self, webhook_key: str, mentioned_list: Optional[list] = None):
        """初始化企业微信通知器

        Args:
            webhook_key: 机器人 webhook key
            mentioned_list: @用户列表，如 ["userid1", "userid2"] 或 ["@all"]
        """
        self.webhook_key = webhook_key
        self.mentioned_list = mentioned_list or []
        self._url = f"{self.WEBHOOK_URL}?key={webhook_key}"

    async def send(self, alert: Alert) -> bool:
        """发送企业微信报警

        Args:
            alert: 报警信息

        Returns:
            是否发送成功
        """
        try:
            return await asyncio.to_thread(self._send_sync, alert)
        except Exception as e:
            logger.error(f"wechat_send_failed", error=str(e))
            return False

    def _send_sync(self, alert: Alert) -> bool:
        """同步发送消息"""
        # 构建 markdown 消息
        level_emoji = {
            AlertLevel.DEBUG: "🐛",
            AlertLevel.INFO: "ℹ️",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.ERROR: "❌",
            AlertLevel.CRITICAL: "🚨",
        }
        emoji = level_emoji.get(alert.level, "📢")

        # 构建详情
        details_text = ""
        if alert.details:
            details_rows = [
                f">**{k}:** {v}"
                for k, v in alert.details.items()
                if k != "severity"
            ]
            details_text = "\n".join(details_rows)

        markdown_content = f"""{emoji} **QuantForge 报警**

**<font color=\"{'warning' if alert.level.priority >= AlertLevel.WARNING.priority else 'info'}\">{alert.title}</font>**

**>时间:** {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
**>级别:** {alert.level.value.upper()}
**>消息:** {alert.message}

{details_text}
"""

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": markdown_content,
            },
        }

        # 添加 @ 用户
        if self.mentioned_list:
            payload["mentioned_list"] = self.mentioned_list

        response = requests.post(
            self._url,
            json=payload,
            timeout=10,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()

        result = response.json()
        if result.get("errcode") == 0:
            logger.info(f"wechat_sent", alert_id=alert.alert_id)
            return True
        else:
            logger.error(f"wechat_error", result=result)
            return False

    def send_text(self, content: str) -> bool:
        """发送纯文本消息

        Args:
            content: 消息内容

        Returns:
            是否发送成功
        """
        payload = {
            "msgtype": "text",
            "text": {
                "content": content,
                "mentioned_list": self.mentioned_list,
            },
        }

        try:
            response = requests.post(
                self._url,
                json=payload,
                timeout=10,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            result = response.json()
            return result.get("errcode") == 0
        except Exception as e:
            logger.error(f"wechat_text_send_failed", error=str(e))
            return False
