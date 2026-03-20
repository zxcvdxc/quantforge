"""
Encryption Module - 加密模块
提供Fernet对称加密、PBKDF2密钥派生等功能
"""

import os
import json
import base64
import hashlib
import secrets
from pathlib import Path
from typing import Dict, Any, Optional, Union, BinaryIO
from dataclasses import dataclass
from datetime import datetime, timedelta
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

from .exceptions import EncryptionError, DecryptionError, KeyRotationError


# 默认配置
DEFAULT_KEY_ITERATIONS = 480000  # PBKDF2迭代次数 (OWASP推荐)
DEFAULT_SALT_LENGTH = 32
DEFAULT_KEY_LENGTH = 32

# 环境变量名
ENV_MASTER_KEY = "QUANTFORGE_MASTER_KEY"
ENV_KEY_FILE = "QUANTFORGE_KEY_FILE"


class KeyDerivation:
    """
    密钥派生类 - 使用PBKDF2
    
    PBKDF2 (Password-Based Key Derivation Function 2) 是一种密钥派生函数，
    用于从密码生成加密密钥，通过多次哈希增加暴力破解难度。
    """
    
    def __init__(
        self,
        iterations: int = DEFAULT_KEY_ITERATIONS,
        salt_length: int = DEFAULT_SALT_LENGTH,
        key_length: int = DEFAULT_KEY_LENGTH,
    ):
        self.iterations = iterations
        self.salt_length = salt_length
        self.key_length = key_length
    
    def generate_salt(self) -> bytes:
        """生成随机盐值"""
        return secrets.token_bytes(self.salt_length)
    
    def derive_key(self, password: str, salt: Optional[bytes] = None) -> tuple:
        """
        从密码派生加密密钥
        
        Args:
            password: 原始密码
            salt: 盐值，若为None则自动生成
            
        Returns:
            (key_bytes, salt) 元组
        """
        if salt is None:
            salt = self.generate_salt()
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.key_length,
            salt=salt,
            iterations=self.iterations,
            backend=default_backend(),
        )
        
        key = kdf.derive(password.encode("utf-8"))
        return key, salt
    
    def derive_key_fernet(self, password: str, salt: Optional[bytes] = None) -> tuple:
        """
        派生Fernet兼容的密钥 (URL-safe base64编码)
        
        Args:
            password: 原始密码
            salt: 盐值，若为None则自动生成
            
        Returns:
            (fernet_key, salt) 元组
        """
        key, salt = self.derive_key(password, salt)
        # Fernet需要32字节、URL-safe base64编码的密钥
        fernet_key = base64.urlsafe_b64encode(key)
        return fernet_key, salt


class FernetEncryption:
    """
    Fernet对称加密类
    
    Fernet是cryptography库提供的一种对称加密方案，特点：
    - 使用AES-128 in CBC mode加密
    - 使用HMAC-SHA256进行认证
    - 密钥通过PBKDF2派生
    - 所有密文都包含时间戳防止重放攻击
    """
    
    def __init__(self, key: Union[str, bytes]):
        """
        初始化加密器
        
        Args:
            key: Fernet密钥 (URL-safe base64编码) 或原始密码
        """
        if isinstance(key, str):
            # 如果是普通字符串，派生密钥
            kdf = KeyDerivation()
            key, _ = kdf.derive_key_fernet(key)
        
        self._fernet = Fernet(key)
    
    @classmethod
    def generate_key(cls) -> str:
        """生成新的随机密钥"""
        return Fernet.generate_key().decode("utf-8")
    
    def encrypt(self, data: Union[str, bytes]) -> str:
        """
        加密数据
        
        Args:
            data: 要加密的数据
            
        Returns:
            base64编码的密文字符串
        """
        try:
            if isinstance(data, str):
                data = data.encode("utf-8")
            encrypted = self._fernet.encrypt(data)
            return encrypted.decode("utf-8")
        except Exception as e:
            raise EncryptionError(f"Encryption failed: {e}")
    
    def decrypt(self, encrypted_data: str) -> str:
        """
        解密数据
        
        Args:
            encrypted_data: 密文字符串
            
        Returns:
            解密后的明文字符串
        """
        try:
            decrypted = self._fernet.decrypt(encrypted_data.encode("utf-8"))
            return decrypted.decode("utf-8")
        except InvalidToken:
            raise DecryptionError("Invalid or expired token")
        except Exception as e:
            raise DecryptionError(f"Decryption failed: {e}")
    
    def encrypt_dict(self, data: Dict[str, Any]) -> str:
        """加密字典数据"""
        json_str = json.dumps(data, ensure_ascii=False)
        return self.encrypt(json_str)
    
    def decrypt_dict(self, encrypted_data: str) -> Dict[str, Any]:
        """解密字典数据"""
        json_str = self.decrypt(encrypted_data)
        return json.loads(json_str)
    
    def encrypt_file(self, input_path: Union[str, Path], output_path: Union[str, Path]) -> None:
        """加密文件"""
        input_path = Path(input_path)
        output_path = Path(output_path)
        
        try:
            with open(input_path, "rb") as f:
                data = f.read()
            encrypted = self._fernet.encrypt(data)
            with open(output_path, "wb") as f:
                f.write(encrypted)
        except Exception as e:
            raise EncryptionError(f"File encryption failed: {e}")
    
    def decrypt_file(self, input_path: Union[str, Path], output_path: Union[str, Path]) -> None:
        """解密文件"""
        input_path = Path(input_path)
        output_path = Path(output_path)
        
        try:
            with open(input_path, "rb") as f:
                data = f.read()
            decrypted = self._fernet.decrypt(data)
            with open(output_path, "wb") as f:
                f.write(decrypted)
        except Exception as e:
            raise DecryptionError(f"File decryption failed: {e}")


@dataclass
class SecureConfig:
    """
    安全配置类
    
    支持两种密钥模式：
    1. 环境变量模式：从环境变量读取主密钥
    2. 密钥文件模式：从加密文件读取密钥
    """
    
    master_key: Optional[str] = None
    key_file: Optional[Path] = None
    encrypted_config_path: Optional[Path] = None
    
    def __post_init__(self):
        if self.master_key is None:
            self.master_key = get_master_key()
        
        if self.master_key is None:
            raise EncryptionError(
                f"Master key not found. Set {ENV_MASTER_KEY} environment variable "
                f"or use initialize_security() to set up."
            )
        
        self._encryption = FernetEncryption(self.master_key)
    
    @property
    def encryption(self) -> FernetEncryption:
        """获取加密器实例"""
        return self._encryption
    
    def encrypt_value(self, value: str) -> str:
        """加密单个值"""
        return self._encryption.encrypt(value)
    
    def decrypt_value(self, encrypted_value: str) -> str:
        """解密单个值"""
        return self._encryption.decrypt(encrypted_value)
    
    def encrypt_config_values(
        self,
        config: Dict[str, Any],
        sensitive_keys: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        加密配置中的敏感字段
        
        Args:
            config: 配置字典
            sensitive_keys: 需要加密的字段列表，默认加密常见敏感字段
            
        Returns:
            加密后的配置字典
        """
        if sensitive_keys is None:
            sensitive_keys = [
                "api_key", "api_secret", "secret", "password", "token",
                "passphrase", "private_key", "access_key", "access_secret",
                "mysql_password", "redis_password", "influxdb_token",
            ]
        
        encrypted_config = {}
        for key, value in config.items():
            if isinstance(value, dict):
                # 递归处理嵌套字典
                encrypted_config[key] = self.encrypt_config_values(value, sensitive_keys)
            elif isinstance(value, list):
                # 处理列表
                encrypted_config[key] = [
                    self.encrypt_config_values(item, sensitive_keys) if isinstance(item, dict) else item
                    for item in value
                ]
            elif isinstance(value, str) and any(sk in key.lower() for sk in sensitive_keys):
                # 加密敏感值
                encrypted_config[key] = f"ENC:{self._encryption.encrypt(value)}"
            else:
                encrypted_config[key] = value
        
        return encrypted_config
    
    def decrypt_config_values(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        解密配置中的加密字段
        
        Args:
            config: 配置字典
            
        Returns:
            解密后的配置字典
        """
        decrypted_config = {}
        for key, value in config.items():
            if isinstance(value, dict):
                # 递归处理嵌套字典
                decrypted_config[key] = self.decrypt_config_values(value)
            elif isinstance(value, list):
                # 处理列表
                decrypted_config[key] = [
                    self.decrypt_config_values(item) if isinstance(item, dict) else item
                    for item in value
                ]
            elif isinstance(value, str) and value.startswith("ENC:"):
                # 解密加密值
                encrypted_value = value[4:]  # 移除 ENC: 前缀
                decrypted_config[key] = self._encryption.decrypt(encrypted_value)
            else:
                decrypted_config[key] = value
        
        return decrypted_config
    
    def save_encrypted_config(self, config: Dict[str, Any], path: Optional[Path] = None) -> None:
        """保存加密配置到文件"""
        path = path or self.encrypted_config_path
        if path is None:
            raise EncryptionError("Config path not specified")
        
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        encrypted_config = self.encrypt_config_values(config)
        with open(path, "w") as f:
            json.dump(encrypted_config, f, indent=2, ensure_ascii=False)
    
    def load_encrypted_config(self, path: Optional[Path] = None) -> Dict[str, Any]:
        """从文件加载加密配置"""
        path = path or self.encrypted_config_path
        if path is None:
            raise EncryptionError("Config path not specified")
        
        path = Path(path)
        if not path.exists():
            raise EncryptionError(f"Config file not found: {path}")
        
        with open(path) as f:
            encrypted_config = json.load(f)
        
        return self.decrypt_config_values(encrypted_config)


def get_master_key() -> Optional[str]:
    """
    获取主密钥
    
    查找顺序：
    1. 环境变量 QUANTFORGE_MASTER_KEY
    2. 密钥文件 (QUANTFORGE_KEY_FILE环境变量指定)
    3. 默认位置 ~/.quantforge/.master_key
    """
    # 1. 环境变量
    key = os.getenv(ENV_MASTER_KEY)
    if key:
        return key
    
    # 2. 密钥文件
    key_file = os.getenv(ENV_KEY_FILE)
    if key_file and Path(key_file).exists():
        with open(key_file) as f:
            return f.read().strip()
    
    # 3. 默认位置
    default_key_file = Path.home() / ".quantforge" / ".master_key"
    if default_key_file.exists():
        with open(default_key_file) as f:
            return f.read().strip()
    
    return None


def generate_master_key() -> str:
    """生成新的主密钥"""
    return FernetEncryption.generate_key()


def save_master_key(key: str, path: Optional[Path] = None) -> None:
    """
    保存主密钥到文件
    
    Args:
        key: 主密钥
        path: 保存路径，默认为 ~/.quantforge/.master_key
    """
    if path is None:
        path = Path.home() / ".quantforge" / ".master_key"
    
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    
    with open(path, "w") as f:
        f.write(key)
    
    # 设置文件权限 (仅所有者可读写)
    os.chmod(path, 0o600)


def initialize_security(password: Optional[str] = None) -> str:
    """
    初始化安全系统
    
    Args:
        password: 可选的密码，若不提供则生成随机密钥
        
    Returns:
        主密钥
    """
    if password:
        # 从密码派生密钥
        kdf = KeyDerivation()
        key, _ = kdf.derive_key_fernet(password)
        key = key.decode("utf-8")
    else:
        # 生成随机密钥
        key = generate_master_key()
    
    # 保存密钥
    save_master_key(key)
    
    return key


def encrypt_config(
    config: Dict[str, Any],
    master_key: Optional[str] = None,
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    加密配置字典
    
    Args:
        config: 配置字典
        master_key: 主密钥，若为None则从环境获取
        output_path: 可选的输出文件路径
        
    Returns:
        加密后的配置字典
    """
    secure_config = SecureConfig(master_key=master_key)
    encrypted = secure_config.encrypt_config_values(config)
    
    if output_path:
        secure_config.save_encrypted_config(config, output_path)
    
    return encrypted


def decrypt_config(
    encrypted_config: Dict[str, Any],
    master_key: Optional[str] = None,
    input_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    解密配置字典
    
    Args:
        encrypted_config: 加密配置字典，若为None则从文件读取
        master_key: 主密钥，若为None则从环境获取
        input_path: 可选的输入文件路径
        
    Returns:
        解密后的配置字典
    """
    secure_config = SecureConfig(master_key=master_key, encrypted_config_path=input_path)
    
    if input_path:
        return secure_config.load_encrypted_config(input_path)
    
    return secure_config.decrypt_config_values(encrypted_config)


def rotate_key(
    old_key: str,
    new_key: Optional[str] = None,
    config_path: Optional[Path] = None,
) -> str:
    """
    密钥轮换
    
    使用新密钥重新加密所有配置
    
    Args:
        old_key: 旧密钥
        new_key: 新密钥，若为None则生成新密钥
        config_path: 配置文件路径
        
    Returns:
        新密钥
    """
    if new_key is None:
        new_key = generate_master_key()
    
    if config_path is None:
        raise KeyRotationError("Config path required for key rotation")
    
    config_path = Path(config_path)
    if not config_path.exists():
        raise KeyRotationError(f"Config file not found: {config_path}")
    
    try:
        # 使用旧密钥解密
        old_secure = SecureConfig(master_key=old_key)
        config = old_secure.load_encrypted_config(config_path)
        
        # 使用新密钥加密
        new_secure = SecureConfig(master_key=new_key)
        new_secure.save_encrypted_config(config, config_path)
        
        return new_key
    except Exception as e:
        raise KeyRotationError(f"Key rotation failed: {e}")
