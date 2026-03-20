"""邮件通知器

通过 SMTP 发送邮件报警。
"""

import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

import structlog

from ..alerts import Alert, AlertLevel, Notifier

logger = structlog.get_logger()


class EmailNotifier:
    """邮件通知器"""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        from_addr: str,
        to_addrs: List[str],
        use_tls: bool = True,
    ):
        """初始化邮件通知器

        Args:
            smtp_host: SMTP 服务器地址
            smtp_port: SMTP 端口
            username: 登录用户名
            password: 登录密码
            from_addr: 发件人地址
            to_addrs: 收件人地址列表
            use_tls: 是否使用 TLS
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_addr = from_addr
        self.to_addrs = to_addrs
        self.use_tls = use_tls

    async def send(self, alert: Alert) -> bool:
        """发送邮件报警

        Args:
            alert: 报警信息

        Returns:
            是否发送成功
        """
        try:
            # 在后台线程中执行 SMTP 操作
            return await asyncio.to_thread(self._send_sync, alert)
        except Exception as e:
            logger.error(f"email_send_failed", error=str(e))
            return False

    def _send_sync(self, alert: Alert) -> bool:
        """同步发送邮件"""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[QuantForge] {alert.title}"
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(self.to_addrs)

        # 纯文本版本
        text_body = alert.format_message()

        # HTML 版本
        html_body = self._format_html(alert)

        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        # 连接 SMTP 服务器
        server = smtplib.SMTP(self.smtp_host, self.smtp_port)
        try:
            if self.use_tls:
                server.starttls()

            server.login(self.username, self.password)
            server.sendmail(self.from_addr, self.to_addrs, msg.as_string())
            logger.info(f"email_sent", alert_id=alert.alert_id, to=self.to_addrs)
            return True
        finally:
            server.quit()

    def _format_html(self, alert: Alert) -> str:
        """格式化 HTML 邮件内容"""
        level_colors = {
            AlertLevel.DEBUG: "#6c757d",
            AlertLevel.INFO: "#0d6efd",
            AlertLevel.WARNING: "#ffc107",
            AlertLevel.ERROR: "#dc3545",
            AlertLevel.CRITICAL: "#212529",
        }
        color = level_colors.get(alert.level, "#0d6efd")

        details_html = ""
        if alert.details:
            rows = "\n".join(
                f"<tr><td><strong>{k}</strong></td><td>{v}</td></tr>"
                for k, v in alert.details.items()
                if k != "severity"
            )
            details_html = f"""
            <h3>详情</h3>
            <table border="1" cellpadding="5" cellspacing="0">
                {rows}
            </table>
            """

        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6;">
            <div style="border-left: 4px solid {color}; padding-left: 15px;">
                <h2 style="color: {color}; margin-top: 0;">{alert.title}</h2>
                <p><strong>级别:</strong> {alert.level.value.upper()}</p>
                <p><strong>时间:</strong> {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p><strong>消息:</strong> {alert.message}</p>
                {details_html}
            </div>
            <hr>
            <p style="color: #6c757d; font-size: 12px;">
                此邮件由 QuantForge 监控系统自动发送
            </p>
        </body>
        </html>
        """
