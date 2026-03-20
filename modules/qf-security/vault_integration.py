#!/usr/bin/env python3
"""
QuantForge Vault 集成模块
支持 HashiCorp Vault 密钥管理
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import hvac  # HashiCorp Vault Python客户端

logger = logging.getLogger(__name__)


@dataclass
class VaultConfig:
    """Vault配置"""
    url: str
    token: Optional[str] = None
    role_id: Optional[str] = None
    secret_id: Optional[str] = None
    namespace: Optional[str] = None
    verify_ssl: bool = True
    timeout: int = 30


class VaultManager:
    """Vault密钥管理器"""
    
    def __init__(self, config: VaultConfig):
        self.config = config
        self.client: Optional[hvac.Client] = None
        self._connected = False
        
    def connect(self) -> bool:
        """连接Vault"""
        try:
            self.client = hvac.Client(
                url=self.config.url,
                namespace=self.config.namespace,
                verify=self.config.verify_ssl,
                timeout=self.config.timeout
            )
            
            # 认证
            if self.config.token:
                self.client.token = self.config.token
            elif self.config.role_id and self.config.secret_id:
                self.client.auth.approle.login(
                    role_id=self.config.role_id,
                    secret_id=self.config.secret_id
                )
            else:
                # 尝试从环境变量获取
                if os.getenv("VAULT_TOKEN"):
                    self.client.token = os.getenv("VAULT_TOKEN")
                else:
                    logger.error("Vault认证信息缺失")
                    return False
            
            # 验证连接
            self._connected = self.client.is_authenticated()
            
            if self._connected:
                logger.info(f"Vault连接成功: {self.config.url}")
            else:
                logger.error("Vault认证失败")
                
            return self._connected
            
        except Exception as e:
            logger.error(f"Vault连接失败: {e}")
            return False
            
    def read_secret(self, path: str, key: Optional[str] = None) -> Any:
        """读取密钥"""
        if not self._connected:
            if not self.connect():
                return None
                
        try:
            response = self.client.secrets.kv.v2.read_secret_version(path=path)
            data = response["data"]["data"]
            
            if key:
                return data.get(key)
            return data
            
        except Exception as e:
            logger.error(f"读取密钥失败 {path}: {e}")
            return None
            
    def write_secret(self, path: str, data: Dict[str, Any]) -> bool:
        """写入密钥"""
        if not self._connected:
            if not self.connect():
                return False
                
        try:
            self.client.secrets.kv.v2.create_or_update_secret(
                path=path,
                secret=data
            )
            logger.info(f"密钥已写入: {path}")
            return True
            
        except Exception as e:
            logger.error(f"写入密钥失败 {path}: {e}")
            return False
            
    def delete_secret(self, path: str) -> bool:
        """删除密钥"""
        if not self._connected:
            if not self.connect():
                return False
                
        try:
            self.client.secrets.kv.v2.delete_metadata_and_all_versions(path=path)
            logger.info(f"密钥已删除: {path}")
            return True
            
        except Exception as e:
            logger.error(f"删除密钥失败 {path}: {e}")
            return False
            
    def list_secrets(self, path: str) -> List[str]:
        """列出密钥"""
        if not self._connected:
            if not self.connect():
                return []
                
        try:
            response = self.client.secrets.kv.v2.list_secrets(path=path)
            return response["data"]["keys"]
        except Exception as e:
            logger.error(f"列出密钥失败 {path}: {e}")
            return []
            
    def rotate_secret(self, path: str, key: str, new_value: str) -> bool:
        """轮换密钥"""
        data = self.read_secret(path)
        if data is None:
            return False
            
        data[key] = new_value
        return self.write_secret(path, data)
        
    def get_database_credentials(self, role: str = "quantforge-app") -> Optional[Dict[str, str]]:
        """获取数据库动态凭证"""
        if not self._connected:
            if not self.connect():
                return None
                
        try:
            response = self.client.secrets.database.generate_credentials(
                name=role
            )
            return {
                "username": response["data"]["username"],
                "password": response["data"]["password"],
                "lease_id": response["lease_id"],
                "lease_duration": response["lease_duration"]
            }
        except Exception as e:
            logger.error(f"获取数据库凭证失败: {e}")
            return None
            
    def renew_lease(self, lease_id: str, increment: int = 3600) -> bool:
        """续租密钥"""
        if not self._connected:
            if not self.connect():
                return False
                
        try:
            self.client.sys.renew_lease(lease_id=lease_id, increment=increment)
            return True
        except Exception as e:
            logger.error(f"续租失败 {lease_id}: {e}")
            return False


class SecretInjector:
    """密钥注入器 - 将Vault密钥注入环境变量或配置文件"""
    
    def __init__(self, vault_manager: VaultManager):
        self.vault = vault_manager
        
    def inject_to_env(self, mappings: Dict[str, str]):
        """
        将Vault密钥注入环境变量
        
        Args:
            mappings: {环境变量名: Vault路径/键}
                     例如: {"MYSQL_PASSWORD": "secret/data/mysql#password"}
        """
        for env_var, vault_path in mappings.items():
            try:
                # 解析路径和键
                if "#" in vault_path:
                    path, key = vault_path.split("#")
                else:
                    path = vault_path
                    key = None
                    
                value = self.vault.read_secret(path, key)
                
                if value:
                    os.environ[env_var] = str(value)
                    logger.info(f"密钥已注入: {env_var}")
                else:
                    logger.warning(f"密钥未找到: {vault_path}")
                    
            except Exception as e:
                logger.error(f"密钥注入失败 {env_var}: {e}")
                
    def inject_to_config(self, config: Dict, mappings: Dict[str, str]) -> Dict:
        """
        将Vault密钥注入配置字典
        
        Args:
            config: 配置字典
            mappings: {配置键: Vault路径/键}
                     例如: {"database.mysql.password": "secret/data/mysql#password"}
        """
        config = config.copy()
        
        for config_key, vault_path in mappings.items():
            try:
                if "#" in vault_path:
                    path, key = vault_path.split("#")
                else:
                    path = vault_path
                    key = None
                    
                value = self.vault.read_secret(path, key)
                
                if value:
                    # 设置嵌套配置值
                    keys = config_key.split(".")
                    current = config
                    for k in keys[:-1]:
                        if k not in current:
                            current[k] = {}
                        current = current[k]
                    current[keys[-1]] = value
                    
                    logger.info(f"配置已更新: {config_key}")
                    
            except Exception as e:
                logger.error(f"配置注入失败 {config_key}: {e}")
                
        return config


# 便捷函数
def create_vault_manager_from_env() -> Optional[VaultManager]:
    """从环境变量创建Vault管理器"""
    config = VaultConfig(
        url=os.getenv("VAULT_ADDR", "http://localhost:8200"),
        token=os.getenv("VAULT_TOKEN"),
        role_id=os.getenv("VAULT_ROLE_ID"),
        secret_id=os.getenv("VAULT_SECRET_ID"),
        namespace=os.getenv("VAULT_NAMESPACE"),
        verify_ssl=os.getenv("VAULT_SKIP_VERIFY", "false").lower() != "true"
    )
    
    return VaultManager(config)


def init_secrets():
    """初始化密钥 - 在应用启动时调用"""
    vault = create_vault_manager_from_env()
    
    if not vault or not vault.connect():
        logger.warning("Vault连接失败，使用本地配置文件")
        return
        
    injector = SecretInjector(vault)
    
    # 定义密钥映射
    mappings = {
        # 数据库
        "MYSQL_PASSWORD": "secret/data/quantforge/mysql#password",
        "MYSQL_ROOT_PASSWORD": "secret/data/quantforge/mysql#root_password",
        "INFLUXDB_TOKEN": "secret/data/quantforge/influxdb#token",
        "INFLUXDB_PASSWORD": "secret/data/quantforge/influxdb#password",
        "REDIS_PASSWORD": "secret/data/quantforge/redis#password",
        
        # 交易所API
        "OKX_API_KEY": "secret/data/quantforge/exchanges/okx#api_key",
        "OKX_API_SECRET": "secret/data/quantforge/exchanges/okx#api_secret",
        "OKX_PASSPHRASE": "secret/data/quantforge/exchanges/okx#passphrase",
        "BINANCE_API_KEY": "secret/data/quantforge/exchanges/binance#api_key",
        "BINANCE_API_SECRET": "secret/data/quantforge/exchanges/binance#api_secret",
        "TUSHARE_TOKEN": "secret/data/quantforge/exchanges/tushare#token",
        
        # 监控
        "GRAFANA_PASSWORD": "secret/data/quantforge/grafana#password",
        "SMTP_PASSWORD": "secret/data/quantforge/alerts/smtp#password",
        "TELEGRAM_BOT_TOKEN": "secret/data/quantforge/alerts/telegram#bot_token",
        
        # 安全
        "JWT_SECRET": "secret/data/quantforge/security#jwt_secret",
        "ENCRYPTION_KEY": "secret/data/quantforge/security#encryption_key",
    }
    
    injector.inject_to_env(mappings)
    logger.info("密钥注入完成")


# Vault策略定义（用于初始化）
VAULT_POLICIES = {
    "quantforge-app": """
        path "secret/data/quantforge/*" {
            capabilities = ["read", "list"]
        }
        path "database/creds/quantforge-app" {
            capabilities = ["read"]
        }
    """,
    "quantforge-admin": """
        path "secret/data/quantforge/*" {
            capabilities = ["create", "read", "update", "delete", "list"]
        }
        path "database/creds/*" {
            capabilities = ["read"]
        }
        path "sys/leases/*" {
            capabilities = ["create", "read", "update", "delete"]
        }
    """
}


if __name__ == "__main__":
    # 测试Vault连接
    vault = create_vault_manager_from_env()
    
    if vault.connect():
        print("✅ Vault连接成功")
        
        # 读取测试密钥
        secret = vault.read_secret("secret/data/quantforge/test")
        print(f"测试密钥: {secret}")
    else:
        print("❌ Vault连接失败")
