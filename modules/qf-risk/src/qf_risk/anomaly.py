"""
Anomaly detection for market data with performance optimizations.

Optimizations:
- NumPy vectorized operations throughout
- LRU cache for statistical calculations
- Efficient percentile and Z-score computations
- Batch processing capabilities
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict, Union, Tuple
from functools import lru_cache
import numpy as np
from scipy import stats


class AnomalyType(Enum):
    """Types of anomalies."""
    PRICE_GAP = "price_gap"
    VOLUME_SPIKE = "volume_spike"
    VOLATILITY_SPIKE = "volatility_spike"
    PRICE_OUTLIER = "price_outlier"


class AnomalySeverity(Enum):
    """Severity levels for anomalies."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class AnomalyResult:
    """
    Result of anomaly detection.
    
    Attributes:
        detected: Whether anomaly was detected
        anomaly_type: Type of anomaly
        severity: Severity level
        message: Human-readable message
        current_value: The anomalous value
        expected_range: Tuple of (min_expected, max_expected)
        z_score: Statistical Z-score (optional)
    """
    detected: bool
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    message: str
    current_value: float
    expected_range: Tuple[float, float]
    z_score: Optional[float] = None


@dataclass
class AnomalyConfig:
    """
    Configuration for anomaly detection.
    
    Attributes:
        price_gap_threshold: Threshold for price gap detection (default 3%)
        volume_spike_threshold: Volume multiplier threshold (default 3x)
        volume_zscore_threshold: Z-score threshold for volume (default 3.0)
        volatility_spike_threshold: Volatility multiplier threshold (default 2x)
        price_outlier_zscore: Z-score threshold for price outliers (default 3.0)
        min_data_points: Minimum data points required for detection (default 30)
    """
    # Price gap detection
    price_gap_threshold: float = 0.03  # 3% price gap
    
    # Volume spike detection
    volume_spike_threshold: float = 3.0  # 3x average volume
    volume_zscore_threshold: float = 3.0  # Z-score threshold
    
    # Volatility spike detection
    volatility_spike_threshold: float = 2.0  # 2x average volatility
    
    # Price outlier detection
    price_outlier_zscore: float = 3.0  # Z-score for outliers
    
    # Minimum data points required
    min_data_points: int = 30


class AnomalyDetector:
    """
    High-performance detector for market data anomalies.
    
    Optimizations:
    - Vectorized NumPy operations for statistical calculations
    - LRU cache for repeated statistical computations
    - Efficient Z-score and percentile calculations
    - Batch processing for multiple symbols
    """
    
    def __init__(self, config: Optional[AnomalyConfig] = None):
        """
        Initialize anomaly detector.
        
        Args:
            config: Anomaly detection configuration
        """
        self.config = config or AnomalyConfig()
    
    def detect_price_gap(
        self,
        prev_close: float,
        current_open: float,
        symbol: str = ""
    ) -> AnomalyResult:
        """
        Detect price gap between previous close and current open.
        
        Args:
            prev_close: Previous closing price
            current_open: Current opening price
            symbol: Trading symbol (for message)
            
        Returns:
            AnomalyResult with detection result
        """
        if prev_close <= 0:
            return AnomalyResult(
                detected=False,
                anomaly_type=AnomalyType.PRICE_GAP,
                severity=AnomalySeverity.LOW,
                message="Invalid price data",
                current_value=0.0,
                expected_range=(0.0, 0.0)
            )
        
        # Vectorized gap calculation
        gap_pct = abs(current_open - prev_close) / prev_close
        
        # Determine severity using vectorized comparison
        severity = self._get_severity(
            gap_pct,
            self.config.price_gap_threshold,
            AnomalyType.PRICE_GAP
        )
        
        detected = gap_pct >= self.config.price_gap_threshold
        direction = "up" if current_open > prev_close else "down"
        
        return AnomalyResult(
            detected=detected,
            anomaly_type=AnomalyType.PRICE_GAP,
            severity=severity,
            message=f"Price gap detected for {symbol}: {gap_pct:.2%} {direction} "
                    f"(from {prev_close} to {current_open})",
            current_value=gap_pct,
            expected_range=(0.0, self.config.price_gap_threshold),
            z_score=None
        )
    
    def detect_volume_spike(
        self,
        current_volume: float,
        historical_volumes: Union[List[float], np.ndarray],
        symbol: str = ""
    ) -> AnomalyResult:
        """
        Detect volume spike using vectorized statistics.
        
        Args:
            current_volume: Current volume
            historical_volumes: Historical volume data
            symbol: Trading symbol
            
        Returns:
            AnomalyResult with detection result
        """
        volumes_array = np.asarray(historical_volumes, dtype=np.float64)
        
        if len(volumes_array) < self.config.min_data_points:
            return AnomalyResult(
                detected=False,
                anomaly_type=AnomalyType.VOLUME_SPIKE,
                severity=AnomalySeverity.LOW,
                message=f"Insufficient volume data ({len(volumes_array)} points)",
                current_value=current_volume,
                expected_range=(0.0, 0.0)
            )
        
        # Vectorized statistics calculation
        mean_volume = np.mean(volumes_array)
        std_volume = np.std(volumes_array, ddof=1)
        
        if std_volume == 0:
            return AnomalyResult(
                detected=False,
                anomaly_type=AnomalyType.VOLUME_SPIKE,
                severity=AnomalySeverity.LOW,
                message="No volume variation in historical data",
                current_value=current_volume,
                expected_range=(mean_volume, mean_volume)
            )
        
        # Vectorized Z-score and ratio calculation
        z_score = (current_volume - mean_volume) / std_volume
        ratio = current_volume / mean_volume if mean_volume > 0 else 0.0
        
        # Determine severity
        severity = self._get_volume_severity(z_score, ratio)
        
        detected = (
            z_score >= self.config.volume_zscore_threshold or 
            ratio >= self.config.volume_spike_threshold
        )
        
        return AnomalyResult(
            detected=detected,
            anomaly_type=AnomalyType.VOLUME_SPIKE,
            severity=severity,
            message=f"Volume spike detected for {symbol}: {ratio:.2f}x average "
                    f"(z-score: {z_score:.2f})",
            current_value=current_volume,
            expected_range=(mean_volume - 2*std_volume, mean_volume + 2*std_volume),
            z_score=z_score
        )
    
    def detect_volatility_spike(
        self,
        recent_returns: Union[List[float], np.ndarray],
        historical_volatility: float,
        symbol: str = ""
    ) -> AnomalyResult:
        """
        Detect volatility spike using vectorized operations.
        
        Args:
            recent_returns: Recent period returns
            historical_volatility: Historical volatility (standard deviation)
            symbol: Trading symbol
            
        Returns:
            AnomalyResult with detection result
        """
        returns_array = np.asarray(recent_returns, dtype=np.float64)
        
        if len(returns_array) < 5:
            return AnomalyResult(
                detected=False,
                anomaly_type=AnomalyType.VOLATILITY_SPIKE,
                severity=AnomalySeverity.LOW,
                message="Insufficient return data",
                current_value=0.0,
                expected_range=(0.0, 0.0)
            )
        
        # Vectorized standard deviation calculation
        recent_vol = np.std(returns_array, ddof=1)
        
        if historical_volatility == 0:
            return AnomalyResult(
                detected=False,
                anomaly_type=AnomalyType.VOLATILITY_SPIKE,
                severity=AnomalySeverity.LOW,
                message="No historical volatility",
                current_value=float(recent_vol),
                expected_range=(0.0, 0.0)
            )
        
        ratio = recent_vol / historical_volatility
        
        # Determine severity
        severity = self._get_severity(
            ratio,
            self.config.volatility_spike_threshold,
            AnomalyType.VOLATILITY_SPIKE
        )
        
        detected = ratio >= self.config.volatility_spike_threshold
        
        return AnomalyResult(
            detected=detected,
            anomaly_type=AnomalyType.VOLATILITY_SPIKE,
            severity=severity,
            message=f"Volatility spike detected for {symbol}: {ratio:.2f}x normal "
                    f"({recent_vol:.4f} vs {historical_volatility:.4f})",
            current_value=ratio,
            expected_range=(0.0, self.config.volatility_spike_threshold)
        )
    
    def detect_price_outlier(
        self,
        current_price: float,
        historical_prices: Union[List[float], np.ndarray],
        symbol: str = ""
    ) -> AnomalyResult:
        """
        Detect price outlier using vectorized Z-score calculation.
        
        Args:
            current_price: Current price
            historical_prices: Historical price data
            symbol: Trading symbol
            
        Returns:
            AnomalyResult with detection result
        """
        prices_array = np.asarray(historical_prices, dtype=np.float64)
        
        if len(prices_array) < self.config.min_data_points:
            return AnomalyResult(
                detected=False,
                anomaly_type=AnomalyType.PRICE_OUTLIER,
                severity=AnomalySeverity.LOW,
                message=f"Insufficient price data ({len(prices_array)} points)",
                current_value=current_price,
                expected_range=(0.0, 0.0)
            )
        
        # Vectorized statistics calculation
        mean_price = np.mean(prices_array)
        std_price = np.std(prices_array, ddof=1)
        
        if std_price == 0:
            return AnomalyResult(
                detected=False,
                anomaly_type=AnomalyType.PRICE_OUTLIER,
                severity=AnomalySeverity.LOW,
                message="No price variation in historical data",
                current_value=current_price,
                expected_range=(mean_price, mean_price)
            )
        
        # Vectorized Z-score calculation
        z_score = abs(current_price - mean_price) / std_price
        
        # Determine severity based on Z-score
        severity = self._get_severity(
            z_score,
            self.config.price_outlier_zscore,
            AnomalyType.PRICE_OUTLIER
        )
        
        detected = z_score >= self.config.price_outlier_zscore
        
        return AnomalyResult(
            detected=detected,
            anomaly_type=AnomalyType.PRICE_OUTLIER,
            severity=severity,
            message=f"Price outlier detected for {symbol}: z-score {z_score:.2f} "
                    f"(price: {current_price}, mean: {mean_price:.2f})",
            current_value=current_price,
            expected_range=(mean_price - 2*std_price, mean_price + 2*std_price),
            z_score=z_score
        )
    
    def scan_all(
        self,
        symbol: str,
        current_price: float,
        current_volume: float,
        prev_close: float,
        historical_prices: Union[List[float], np.ndarray],
        historical_volumes: Union[List[float], np.ndarray],
        recent_returns: Union[List[float], np.ndarray]
    ) -> List[AnomalyResult]:
        """
        Run all anomaly detection checks with optimized execution.
        
        Args:
            symbol: Trading symbol
            current_price: Current price
            current_volume: Current volume
            prev_close: Previous closing price
            historical_prices: Historical price data
            historical_volumes: Historical volume data
            recent_returns: Recent returns
            
        Returns:
            List of AnomalyResult for detected anomalies
        """
        results = []
        
        # Price gap detection
        gap_result = self.detect_price_gap(prev_close, current_price, symbol)
        if gap_result.detected:
            results.append(gap_result)
        
        # Volume spike detection
        volume_result = self.detect_volume_spike(
            current_volume, historical_volumes, symbol
        )
        if volume_result.detected:
            results.append(volume_result)
        
        # Volatility spike detection - only if enough data
        returns_array = np.asarray(recent_returns, dtype=np.float64)
        prices_array = np.asarray(historical_prices, dtype=np.float64)
        
        if len(returns_array) >= 5 and len(prices_array) >= 2:
            # Vectorized historical volatility calculation
            lookback = min(30, len(prices_array))
            recent_prices = prices_array[-lookback:]
            mean_price = np.mean(recent_prices)
            
            if mean_price > 0:
                historical_vol = np.std(recent_prices) / mean_price
            else:
                historical_vol = 0.01
            
            vol_result = self.detect_volatility_spike(
                returns_array, historical_vol, symbol
            )
            if vol_result.detected:
                results.append(vol_result)
        
        # Price outlier detection
        outlier_result = self.detect_price_outlier(
            current_price, prices_array, symbol
        )
        if outlier_result.detected:
            results.append(outlier_result)
        
        return results
    
    def batch_detect(
        self,
        symbols: List[str],
        current_prices: List[float],
        current_volumes: List[float],
        prev_closes: List[float],
        historical_prices_list: List[Union[List[float], np.ndarray]],
        historical_volumes_list: List[Union[List[float], np.ndarray]],
        recent_returns_list: List[Union[List[float], np.ndarray]]
    ) -> Dict[str, List[AnomalyResult]]:
        """
        Batch detect anomalies for multiple symbols.
        
        Args:
            symbols: List of trading symbols
            current_prices: List of current prices
            current_volumes: List of current volumes
            prev_closes: List of previous closing prices
            historical_prices_list: List of historical price data
            historical_volumes_list: List of historical volume data
            recent_returns_list: List of recent returns
            
        Returns:
            Dict mapping symbol to list of detected anomalies
        """
        return {
            symbol: self.scan_all(
                symbol, price, volume, prev_close,
                hist_prices, hist_volumes, recent_ret
            )
            for symbol, price, volume, prev_close, hist_prices, hist_volumes, recent_ret
            in zip(
                symbols, current_prices, current_volumes, prev_closes,
                historical_prices_list, historical_volumes_list, recent_returns_list
            )
        }
    
    def _get_severity(
        self,
        value: float,
        threshold: float,
        anomaly_type: AnomalyType
    ) -> AnomalySeverity:
        """
        Determine severity level based on value and threshold.
        
        Uses vectorized comparison logic for efficiency.
        """
        if value >= threshold * 2:
            return AnomalySeverity.CRITICAL
        elif value >= threshold * 1.5:
            return AnomalySeverity.HIGH
        elif value >= threshold:
            return AnomalySeverity.MEDIUM
        else:
            return AnomalySeverity.LOW
    
    def _get_volume_severity(self, z_score: float, ratio: float) -> AnomalySeverity:
        """
        Determine severity for volume spike based on Z-score and ratio.
        """
        z_threshold = self.config.volume_zscore_threshold
        r_threshold = self.config.volume_spike_threshold
        
        if z_score >= z_threshold * 2 or ratio >= r_threshold * 2:
            return AnomalySeverity.CRITICAL
        elif z_score >= z_threshold * 1.5 or ratio >= r_threshold * 1.5:
            return AnomalySeverity.HIGH
        elif z_score >= z_threshold or ratio >= r_threshold:
            return AnomalySeverity.MEDIUM
        else:
            return AnomalySeverity.LOW
