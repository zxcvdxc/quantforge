# ============================================================
# QuantForge 配置热更新模块
# 支持动态配置更新，无需重启服务
# ============================================================

import os
import yaml
import json
import time
import logging
import hashlib
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading

logger = logging.getLogger(__name__)


@dataclass
class ConfigChange:
    """配置变更"""
    key: str
    old_value: Any
    new_value: Any
    timestamp: float


@dataclass
class FeatureFlags:
    """特性开关"""
    enable_real_trading: bool = False
    enable_notifications: bool = True
    enable_auto_rebalance: bool = True
    enable_ml_models: bool = False
    enable_streaming_data: bool = True
    enable_batch_processing: bool = True
    cache_enabled: bool = True
    hot_reload: bool = False
    detailed_logging: bool = False


class ConfigHotReload:
    """配置热更新管理器"""
    
    def __init__(self, config_path: str, environment: str = "development"):
        self.config_path = Path(config_path)
        self.environment = environment
        self._config: Dict[str, Any] = {}
        self._config_hash: str = ""
        self._lock = threading.RLock()
        self._observers: List[Callable] = []
        self._watchdog_observer: Optional[Observer] = None
        self._running = False
        self._feature_flags = FeatureFlags()
        self._change_history: List[ConfigChange] = []
        
    def load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            # 1. 加载基础配置
            base_config = self._load_yaml(self.config_path / "config.yaml")
            
            # 2. 加载环境特定配置
            env_config = self._load_yaml(
                self.config_path / "environments" / f"{self.environment}.yaml"
            )
            
            # 3. 合并配置
            config = self._deep_merge(base_config or {}, env_config or {})
            
            # 4. 应用环境变量覆盖
            config = self._apply_env_overrides(config)
            
            # 5. 计算配置哈希
            config_str = json.dumps(config, sort_keys=True)
            new_hash = hashlib.sha256(config_str.encode()).hexdigest()
            
            with self._lock:
                if new_hash != self._config_hash:
                    old_config = self._config.copy()
                    self._config = config
                    self._config_hash = new_hash
                    
                    # 检测变更
                    changes = self._detect_changes(old_config, config)
                    if changes:
                        self._change_history.extend(changes)
                        self._notify_observers(changes)
                        
                    # 更新特性开关
                    self._update_feature_flags()
                    
                    logger.info(f"配置已加载/更新 [环境: {self.environment}]")
                    
            return config
            
        except Exception as e:
            logger.error(f"配置加载失败: {e}")
            return self._config  # 返回旧配置
            
    def _load_yaml(self, path: Path) -> Optional[Dict]:
        """加载YAML文件"""
        if not path.exists():
            return None
            
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"加载YAML失败 {path}: {e}")
            return None
            
    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """深度合并字典"""
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
                
        return result
        
    def _apply_env_overrides(self, config: Dict) -> Dict:
        """应用环境变量覆盖"""
        def resolve_env_vars(obj):
            if isinstance(obj, dict):
                return {k: resolve_env_vars(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [resolve_env_vars(item) for item in obj]
            elif isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
                # 解析 ${VAR:default} 格式
                inner = obj[2:-1]
                if ":" in inner:
                    var_name, default = inner.split(":", 1)
                else:
                    var_name, default = inner, ""
                return os.getenv(var_name, default)
            else:
                return obj
                
        return resolve_env_vars(config)
        
    def _detect_changes(self, old: Dict, new: Dict, prefix: str = "") -> List[ConfigChange]:
        """检测配置变更"""
        changes = []
        
        all_keys = set(old.keys()) | set(new.keys())
        
        for key in all_keys:
            full_key = f"{prefix}.{key}" if prefix else key
            old_val = old.get(key)
            new_val = new.get(key)
            
            if isinstance(old_val, dict) and isinstance(new_val, dict):
                changes.extend(self._detect_changes(old_val, new_val, full_key))
            elif old_val != new_val:
                changes.append(ConfigChange(
                    key=full_key,
                    old_value=old_val,
                    new_value=new_val,
                    timestamp=time.time()
                ))
                
        return changes
        
    def _notify_observers(self, changes: List[ConfigChange]):
        """通知观察者"""
        for callback in self._observers:
            try:
                callback(changes)
            except Exception as e:
                logger.error(f"配置变更通知失败: {e}")
                
    def _update_feature_flags(self):
        """更新特性开关"""
        features = self._config.get("features", {})
        
        self._feature_flags = FeatureFlags(
            enable_real_trading=features.get("enable_real_trading", False),
            enable_notifications=features.get("enable_notifications", True),
            enable_auto_rebalance=features.get("enable_auto_rebalance", True),
            enable_ml_models=features.get("enable_ml_models", False),
            enable_streaming_data=features.get("enable_streaming_data", True),
            enable_batch_processing=features.get("enable_batch_processing", True),
            cache_enabled=features.get("cache_enabled", True),
            hot_reload=features.get("hot_reload", False),
            detailed_logging=features.get("detailed_logging", False)
        )
        
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        with self._lock:
            keys = key.split(".")
            value = self._config
            
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
                    
            return value
            
    def get_all(self) -> Dict[str, Any]:
        """获取所有配置"""
        with self._lock:
            return self._config.copy()
            
    def get_feature_flags(self) -> FeatureFlags:
        """获取特性开关"""
        return self._feature_flags
        
    def is_feature_enabled(self, feature_name: str) -> bool:
        """检查特性是否启用"""
        return getattr(self._feature_flags, feature_name, False)
        
    def subscribe(self, callback: Callable[[List[ConfigChange]], None]):
        """订阅配置变更"""
        self._observers.append(callback)
        
    def unsubscribe(self, callback: Callable):
        """取消订阅"""
        if callback in self._observers:
            self._observers.remove(callback)
            
    def start_watching(self):
        """开始监听文件变化"""
        if self._running:
            return
            
        self._running = True
        
        # 使用watchdog监听文件变化
        class ConfigFileHandler(FileSystemEventHandler):
            def __init__(self, reload_callback):
                self.reload_callback = reload_callback
                self.last_reload = 0
                
            def on_modified(self, event):
                if event.is_directory:
                    return
                if event.src_path.endswith(('.yaml', '.yml', '.json')):
                    # 防抖
                    now = time.time()
                    if now - self.last_reload > 1:
                        self.last_reload = now
                        time.sleep(0.1)  # 等待文件写入完成
                        self.reload_callback()
                        
        handler = ConfigFileHandler(self.load_config)
        self._watchdog_observer = Observer()
        self._watchdog_observer.schedule(handler, str(self.config_path), recursive=True)
        self._watchdog_observer.start()
        
        logger.info("配置热更新监听已启动")
        
    def stop_watching(self):
        """停止监听文件变化"""
        self._running = False
        if self._watchdog_observer:
            self._watchdog_observer.stop()
            self._watchdog_observer.join()
            logger.info("配置热更新监听已停止")
            
    def get_change_history(self, limit: int = 100) -> List[ConfigChange]:
        """获取变更历史"""
        return self._change_history[-limit:]
        
    def reload(self):
        """手动重新加载配置"""
        logger.info("手动触发配置重载")
        return self.load_config()


# 全局配置管理器实例
_config_manager: Optional[ConfigHotReload] = None


def init_config(config_path: str = None, environment: str = None) -> ConfigHotReload:
    """初始化配置管理器"""
    global _config_manager
    
    if _config_manager is None:
        config_path = config_path or os.getenv("CONFIG_PATH", "./config")
        environment = environment or os.getenv("ENVIRONMENT", "development")
        
        _config_manager = ConfigHotReload(config_path, environment)
        _config_manager.load_config()
        
    return _config_manager


def get_config(key: str = None, default: Any = None) -> Any:
    """获取配置值"""
    manager = init_config()
    
    if key is None:
        return manager.get_all()
        
    return manager.get(key, default)


def get_feature_flags() -> FeatureFlags:
    """获取特性开关"""
    manager = init_config()
    return manager.get_feature_flags()


def is_feature_enabled(feature_name: str) -> bool:
    """检查特性是否启用"""
    manager = init_config()
    return manager.is_feature_enabled(feature_name)


def reload_config():
    """重新加载配置"""
    manager = init_config()
    return manager.reload()


# 便捷的特性检查函数
def can_trade() -> bool:
    """检查是否可以实盘交易"""
    return is_feature_enabled("enable_real_trading")


def can_send_notifications() -> bool:
    """检查是否可以发送通知"""
    return is_feature_enabled("enable_notifications")


def can_auto_rebalance() -> bool:
    """检查是否可以自动再平衡"""
    return is_feature_enabled("enable_auto_rebalance")


def can_use_ml() -> bool:
    """检查是否可以使用ML模型"""
    return is_feature_enabled("enable_ml_models")


def is_cache_enabled() -> bool:
    """检查缓存是否启用"""
    return is_feature_enabled("cache_enabled")


# 示例用法
if __name__ == "__main__":
    # 初始化
    config = init_config("./config", "development")
    
    # 获取配置
    db_host = get_config("database.mysql.host", "localhost")
    print(f"数据库主机: {db_host}")
    
    # 检查特性
    if can_trade():
        print("实盘交易已启用")
    else:
        print("实盘交易已禁用 (模拟模式)")
        
    # 订阅配置变更
    def on_config_change(changes):
        print("配置已变更:")
        for change in changes:
            print(f"  {change.key}: {change.old_value} -> {change.new_value}")
            
    config.subscribe(on_config_change)
    
    # 启动热更新监听
    config.start_watching()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        config.stop_watching()
