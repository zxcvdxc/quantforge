"""
数据清洗模块
提供数据质量检查、缺失值处理、异常值检测等功能
"""
from typing import List, Optional, Dict, Any, Callable, Union, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from .types import KlineData, TickData
from .exceptions import DataCleaningError


class DataCleaner:
    """数据清洗器
    
    提供金融数据清洗功能：
    - 缺失值检测和处理
    - 异常值检测和过滤
    - 数据格式标准化
    - 时间序列对齐
    - 重复数据处理
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化数据清洗器
        
        Args:
            config: 配置字典
                {
                    "outlier_std_threshold": 3,  # 标准差异常值阈值
                    "max_price_gap": 0.1,        # 最大价格跳变比例
                    "min_volume": 0,             # 最小成交量
                    "fill_missing": "linear",    # 缺失值填充方法
                }
        """
        self.config = config or {}
        self.outlier_std_threshold = self.config.get("outlier_std_threshold", 3.0)
        self.max_price_gap = self.config.get("max_price_gap", 0.1)
        self.min_volume = self.config.get("min_volume", 0)
        self.fill_missing = self.config.get("fill_missing", "linear")
    
    def clean_kline_dataframe(
        self,
        df: pd.DataFrame,
        remove_outliers: bool = True,
        fill_missing: bool = True,
        remove_duplicates: bool = True
    ) -> pd.DataFrame:
        """清洗K线DataFrame
        
        Args:
            df: 原始K线数据DataFrame
            remove_outliers: 是否移除异常值
            fill_missing: 是否填充缺失值
            remove_duplicates: 是否移除重复数据
        
        Returns:
            清洗后的DataFrame
        """
        if df.empty:
            return df
        
        df = df.copy()
        
        # 确保必要的列存在
        required_cols = ["open", "high", "low", "close", "volume"]
        for col in required_cols:
            if col not in df.columns:
                raise DataCleaningError(f"Missing required column: {col}")
        
        # 移除重复数据
        if remove_duplicates:
            df = self._remove_duplicates(df)
        
        # 排序
        if not df.index.is_monotonic_increasing:
            df.sort_index(inplace=True)
        
        # 数据类型转换
        df = self._convert_dtypes(df)
        
        # 检查并修复OHLC逻辑错误
        df = self._fix_ohlc_logic(df)
        
        # 移除异常值
        if remove_outliers:
            df = self._remove_price_outliers(df)
            df = self._remove_volume_outliers(df)
        
        # 填充缺失值
        if fill_missing:
            df = self._fill_missing_values(df)
        
        # 过滤低成交量
        if self.min_volume > 0:
            df = df[df["volume"] >= self.min_volume]
        
        return df
    
    def clean_klines(
        self,
        klines: List[KlineData],
        **kwargs
    ) -> List[KlineData]:
        """清洗K线数据列表
        
        Args:
            klines: K线数据列表
            **kwargs: 传递给clean_kline_dataframe的参数
        
        Returns:
            清洗后的K线数据列表
        """
        if not klines:
            return klines
        
        # 转换为DataFrame处理
        df = pd.DataFrame([k.to_dict() for k in klines])
        if "timestamp" in df.columns:
            df.set_index("timestamp", inplace=True)
        
        df = self.clean_kline_dataframe(df, **kwargs)
        
        # 转换回KlineData列表
        df_reset = df.reset_index()
        return [KlineData.from_dict(row.to_dict()) for _, row in df_reset.iterrows()]
    
    def _remove_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        """移除重复数据"""
        # 基于索引去重（保留最后一条）
        return df[~df.index.duplicated(keep="last")]
    
    def _convert_dtypes(self, df: pd.DataFrame) -> pd.DataFrame:
        """转换数据类型"""
        numeric_cols = ["open", "high", "low", "close", "volume", "quote_volume"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    
    def _fix_ohlc_logic(self, df: pd.DataFrame) -> pd.DataFrame:
        """修复OHLC逻辑错误
        
        确保：
        - high >= max(open, close, low)
        - low <= min(open, close, high)
        """
        # 修复high
        df["high"] = df[["open", "high", "low", "close"]].max(axis=1)
        # 修复low
        df["low"] = df[["open", "high", "low", "close"]].min(axis=1)
        return df
    
    def _remove_price_outliers(self, df: pd.DataFrame) -> pd.DataFrame:
        """移除价格异常值
        
        检测方法：
        1. 基于标准差的异常值检测
        2. 价格跳变检测（与前一根K线的价格变化比例）
        """
        if len(df) < 2:
            return df
        
        # 计算收益率
        df["returns"] = df["close"].pct_change().abs()
        
        # 方法1：标准差异常值
        mean_return = df["returns"].mean()
        std_return = df["returns"].std()
        if std_return > 0:
            outlier_mask = df["returns"] > (mean_return + self.outlier_std_threshold * std_return)
            df = df[~outlier_mask]
        
        # 方法2：价格跳变检测
        df["price_gap"] = df["returns"] > self.max_price_gap
        df = df[~df["price_gap"]]
        
        # 清理临时列
        df = df.drop(columns=["returns", "price_gap"], errors="ignore")
        
        return df
    
    def _remove_volume_outliers(self, df: pd.DataFrame) -> pd.DataFrame:
        """移除成交量异常值"""
        if "volume" not in df.columns or len(df) < 2:
            return df
        
        mean_vol = df["volume"].mean()
        std_vol = df["volume"].std()
        
        if std_vol > 0:
            # 成交量超过均值+3倍标准差视为异常
            outlier_mask = df["volume"] > (mean_vol + self.outlier_std_threshold * std_vol)
            # 不删除，而是设为NaN后续填充
            df.loc[outlier_mask, "volume"] = np.nan
        
        return df
    
    def _fill_missing_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """填充缺失值"""
        if df.empty:
            return df
        
        # 检查时间序列是否有缺失
        if isinstance(df.index, pd.DatetimeIndex):
            df = self._fill_missing_timestamps(df)
        
        # 填充数值缺失
        numeric_cols = ["open", "high", "low", "close", "volume", "quote_volume"]
        
        for col in numeric_cols:
            if col in df.columns:
                if self.fill_missing == "linear":
                    df[col] = df[col].interpolate(method="linear")
                elif self.fill_missing == "ffill":
                    df[col] = df[col].ffill()
                elif self.fill_missing == "bfill":
                    df[col] = df[col].bfill()
                else:
                    df[col] = df[col].fillna(0)
        
        # 对于OHLC，缺失值用close填充
        for col in ["open", "high", "low"]:
            if col in df.columns:
                df[col] = df[col].fillna(df["close"])
        
        # 删除仍有缺失的行
        df = df.dropna(subset=["close"])
        
        return df
    
    def _fill_missing_timestamps(self, df: pd.DataFrame) -> pd.DataFrame:
        """填充缺失的时间戳"""
        if len(df) < 2:
            return df
        
        # 计算时间间隔
        freq = pd.infer_freq(df.index)
        
        if freq:
            # 重新索引到完整的时间序列
            full_range = pd.date_range(start=df.index.min(), end=df.index.max(), freq=freq)
            df = df.reindex(full_range)
            df.index.name = "timestamp"
        
        return df
    
    def clean_tick_dataframe(
        self,
        df: pd.DataFrame,
        remove_duplicates: bool = True,
        remove_outliers: bool = True
    ) -> pd.DataFrame:
        """清洗Tick数据DataFrame"""
        if df.empty:
            return df
        
        df = df.copy()
        
        # 移除重复
        if remove_duplicates:
            df = self._remove_duplicates(df)
        
        # 排序
        if not df.index.is_monotonic_increasing:
            df.sort_index(inplace=True)
        
        # 转换类型
        numeric_cols = ["price", "volume", "bid_price", "ask_price", "bid_volume", "ask_volume"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        
        # 移除价格异常值
        if remove_outliers and len(df) > 2:
            mean_price = df["price"].mean()
            std_price = df["price"].std()
            if std_price > 0:
                df = df[df["price"] <= mean_price + self.outlier_std_threshold * std_price]
                df = df[df["price"] >= mean_price - self.outlier_std_threshold * std_price]
        
        return df
    
    def resample_klines(
        self,
        df: pd.DataFrame,
        target_interval: str
    ) -> pd.DataFrame:
        """K线数据重采样
        
        将高频K线转换为低频K线，如1分钟转为5分钟
        
        Args:
            df: 原始K线DataFrame
            target_interval: 目标周期，如 "5T", "1H", "1D"
        
        Returns:
            重采样后的DataFrame
        """
        if df.empty:
            return df
        
        # 确保索引是DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            raise DataCleaningError("DataFrame index must be DatetimeIndex for resampling")
        
        # 重采样规则
        rules = {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "quote_volume": "sum",
            "trades": "sum",
            "buy_volume": "sum",
            "sell_volume": "sum",
        }
        
        # 选择存在的列
        agg_rules = {col: rule for col, rule in rules.items() if col in df.columns}
        
        resampled = df.resample(target_interval).agg(agg_rules)
        
        # 删除无数据的行
        resampled = resampled.dropna(subset=["close"])
        
        return resampled
    
    def merge_kline_sources(
        self,
        sources: Dict[str, pd.DataFrame],
        method: str = "vwap"
    ) -> pd.DataFrame:
        """合并多个数据源的K线数据
        
        Args:
            sources: 数据源字典，{source_name: dataframe}
            method: 合并方法，"vwap"=成交量加权平均, "mean"=简单平均, "median"=中位数
        
        Returns:
            合并后的DataFrame
        """
        if not sources:
            return pd.DataFrame()
        
        # 对齐时间索引
        all_indices = set()
        for df in sources.values():
            all_indices.update(df.index)
        
        common_index = sorted(all_indices)
        
        # 创建合并结果
        merged = pd.DataFrame(index=common_index)
        
        for col in ["open", "high", "low", "close", "volume"]:
            col_data = []
            
            for name, df in sources.items():
                if col in df.columns:
                    df_aligned = df.reindex(common_index)
                    col_data.append(df_aligned[col])
            
            if col_data:
                if method == "vwap" and col == "close":
                    # 成交量加权平均
                    weights = []
                    prices = []
                    for name, df in sources.items():
                        if col in df.columns and "volume" in df.columns:
                            df_aligned = df.reindex(common_index)
                            weights.append(df_aligned["volume"].fillna(0))
                            prices.append(df_aligned[col])
                    
                    if weights and prices:
                        total_weight = sum(weights)
                        weighted_sum = sum(p * w for p, w in zip(prices, weights))
                        merged[col] = weighted_sum / total_weight.replace(0, np.nan)
                elif method == "mean":
                    merged[col] = pd.concat(col_data, axis=1).mean(axis=1)
                elif method == "median":
                    merged[col] = pd.concat(col_data, axis=1).median(axis=1)
                else:
                    merged[col] = pd.concat(col_data, axis=1).mean(axis=1)
        
        return merged.dropna(subset=["close"])
    
    def detect_gaps(
        self,
        df: pd.DataFrame,
        max_gap: Optional[timedelta] = None
    ) -> List[Tuple[datetime, datetime]]:
        """检测数据缺口
        
        Args:
            df: K线DataFrame
            max_gap: 最大允许的时间间隔
        
        Returns:
            缺口列表，每项为 (start, end)
        """
        if df.empty or not isinstance(df.index, pd.DatetimeIndex):
            return []
        
        if max_gap is None:
            # 自动推断间隔
            if len(df) >= 2:
                typical_gap = df.index.to_series().diff().median()
                max_gap = typical_gap * 2
            else:
                return []
        
        gaps = []
        diff = df.index.to_series().diff()
        gap_indices = diff[diff > max_gap].index
        
        for idx in gap_indices:
            prev_idx = df.index[df.index.get_loc(idx) - 1]
            gaps.append((prev_idx, idx))
        
        return gaps
    
    def validate_data_quality(self, df: pd.DataFrame) -> Dict[str, Any]:
        """验证数据质量
        
        Returns:
            质量报告字典
        """
        report = {
            "total_rows": len(df),
            "missing_values": {},
            "outliers": {},
            "duplicates": 0,
            "gaps": [],
            "score": 100,  # 数据质量分数
        }
        
        if df.empty:
            report["score"] = 0
            return report
        
        # 缺失值统计
        for col in df.columns:
            missing = df[col].isna().sum()
            if missing > 0:
                report["missing_values"][col] = missing
                report["score"] -= min(20, missing / len(df) * 100)
        
        # 重复数据
        report["duplicates"] = df.index.duplicated().sum()
        report["score"] -= min(20, report["duplicates"] / len(df) * 100)
        
        # 缺口检测
        if isinstance(df.index, pd.DatetimeIndex):
            report["gaps"] = self.detect_gaps(df)
            report["score"] -= min(30, len(report["gaps"]) * 5)
        
        # 异常值
        if "close" in df.columns and len(df) > 2:
            returns = df["close"].pct_change().abs()
            mean_return = returns.mean()
            std_return = returns.std()
            if std_return > 0:
                outliers = (returns > mean_return + 3 * std_return).sum()
                report["outliers"]["price"] = int(outliers)
                report["score"] -= min(20, outliers / len(df) * 100)
        
        report["score"] = max(0, report["score"])
        
        return report
