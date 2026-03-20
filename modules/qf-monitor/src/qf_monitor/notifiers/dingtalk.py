"""钉钉通知器

通过钉钉机器人发送报警。
"""

import asyncio
import base64
import hashlib
import hmac
import time
import urllib.parse
from typing import Optional

import requests
import structlog

from ..alerts import Alert, AlertLevel, Notifier

logger = structlog.get_logger()


class DingTalkNotifier:
    """钉钉机器人通知器"""

    WEBHOOK_URL = "https://oapi.dingtalk.com/robot/send"

    def __init__(
        self,
        access_token: str,
        secret: Optional[str] = None,
        at_mobiles: Optional[list] = None,
        at_all: bool = False,
    ):
        """初始化钉钉通知器

        Args:
            access_token: 机器人 access token
            secret: 加签密钥（可选）
            at_mobiles: @手机号列表
            at_all: 是否 @所有人
        """
        self.access_token = access_token
        self.secret = secret
        self.at_mobiles = at_mobiles or []
        self.at_all = at_all

    def _generate_sign(self) -> tuple[str, str]:
        """生成签名

        Returns:
            (timestamp, sign)
        """
        timestamp = str(round(time.time() * 1000))
        if not self.secret:
            return timestamp, ""

        string_to_sign = f"{timestamp}\n{self.secret}"
        sign = (
            base64.b64encode(
                hmac.new(
                    self.secret.encode("utf-8"),
                    string_to_sign.encode("utf-8"),
                    digestmod=hashlib.sha256,
                ).digest()
            )
            .decode("utf-8")
        )
        return timestamp, urllib.parse.quote_plus(sign)

    async def send(self, alert: Alert) -> bool:
        """发送钉钉报警

        Args:
            alert: 报警信息

        Returns:
            是否发送成功
        """
        try:
            return await asyncio.to_thread(self._send_sync, alert)
        except Exception as e:
            logger.error(f"dingtalk_send_failed", error=str(e))
            return False

    def _send_sync(self, alert: Alert) -> bool:
        """同步发送消息"""
        # 构建 webhook URL
        timestamp, sign = self._generate_sign()
        url = f"{self.WEBHOOK_URL}?access_token={self.access_token}"
        if sign:
            url += f"&timestamp={timestamp}&sign={sign}"

        # 级别颜色
        level_colors = {
            AlertLevel.DEBUG: "#909399",
            AlertLevel.INFO: "#409EFF",
            AlertLevel.WARNING: "#E6A23C",
            AlertLevel.ERROR: "#F56C6C",
            AlertLevel.CRITICAL: "#303133",
        }
        color = level_colors.get(alert.level, "#409EFF")

        # 构建详情
        detail_items = []
        if alert.details:
            for k, v in alert.details.items():
                if k != "severity":
                    detail_items.append(f"- **{k}:** {v}")
        details_markdown = "\n".join(detail_items)

        # 构建 markdown 消息
        title = alert.title
        markdown_text = f"""### QuantForge 报警

**<font color=\"{color}\">{title}</font>**

- **时间:** {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
- **级别:** {alert.level.value.upper()}
- **消息:** {alert.message}

{details_markdown}
"""

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": markdown_text,
            },
            "at": {
                "atMobiles": self.at_mobiles,
                "isAtAll": self.at_all,
            },
        }

        response = requests.post(
            url,
            json=payload,
            timeout=10,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()

        result = response.json()
        if result.get("errcode") == 0:
            logger.info(f"dingtalk_sent", alert_id=alert.alert_id)
            return True
        else:
            logger.error(f"dingtalk_error", result=result)
            return False

    def send_text(self, content: str) -> bool:
        """发送纯文本消息

        Args:
            content: 消息内容

        Returns:
            是否发送成功
        """
        timestamp, sign = self._generate_sign()
        url = f"{self.WEBHOOK_URL}?access_token={self.access_token}"
        if sign:
            url += f"&timestamp={timestamp}&sign={sign}"

        payload = {
            "msgtype": "text",
            "text": {"content": content},
            "at": {
                "atMobiles": self.at_mobiles,
                "isAtAll": self.at_all,
            },
        }

        try:
            response = requests.post(
                url,
                json=payload,
                timeout=10,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            result = response.json()
            return result.get("errcode") == 0
        except Exception as e:
            logger.error(f"dingtalk_text_send_failed", error=str(e))
            return False
