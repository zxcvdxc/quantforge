"""Anomaly detection for market data."""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict
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


@dataclass
class AnomalyResult:
    """Result of anomaly detection."""
    detected: bool
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    message: str
    current_value: float
    expected_range: tuple
    z_score: Optional[float] = None


@dataclass
class AnomalyConfig:
    """Configuration for anomaly detection."""
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
    """Detector for market data anomalies."""
    
    def __init__(self, config: Optional[AnomalyConfig] = None):
        self.config = config or AnomalyConfig()
    
    def detect_price_gap(
        self,
        prev_close: float,
        current_open: float,
        symbol: str = ""
    ) -> AnomalyResult:
        """Detect price gap between previous close and current open.
        
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
        
        gap_pct = abs(current_open - prev_close) / prev_close
        
        # Determine severity
        if gap_pct >= self.config.price_gap_threshold * 2:
            severity = AnomalySeverity.CRITICAL
        elif gap_pct >= self.config.price_gap_threshold * 1.5:
            severity = AnomalySeverity.HIGH
        elif gap_pct >= self.config.price_gap_threshold:
            severity = AnomalySeverity.MEDIUM
        else:
            severity = AnomalySeverity.LOW
        
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
        historical_volumes: List[float],
        symbol: str = ""
    ) -> AnomalyResult:
        """Detect volume spike.
        
        Args:
            current_volume: Current volume
            historical_volumes: Historical volume data
            symbol: Trading symbol
            
        Returns:
            AnomalyResult with detection result
        """
        if len(historical_volumes) < self.config.min_data_points:
            return AnomalyResult(
                detected=False,
                anomaly_type=AnomalyType.VOLUME_SPIKE,
                severity=AnomalySeverity.LOW,
                message=f"Insufficient volume data ({len(historical_volumes)} points)",
                current_value=current_volume,
                expected_range=(0.0, 0.0)
            )
        
        volumes_array = np.array(historical_volumes)
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
        
        z_score = (current_volume - mean_volume) / std_volume
        ratio = current_volume / mean_volume if mean_volume > 0 else 0
        
        # Determine severity
        if z_score >= self.config.volume_zscore_threshold * 2 or ratio >= self.config.volume_spike_threshold * 2:
            severity = AnomalySeverity.CRITICAL
        elif z_score >= self.config.volume_zscore_threshold * 1.5 or ratio >= self.config.volume_spike_threshold * 1.5:
            severity = AnomalySeverity.HIGH
        elif z_score >= self.config.volume_zscore_threshold or ratio >= self.config.volume_spike_threshold:
            severity = AnomalySeverity.MEDIUM
        else:
            severity = AnomalySeverity.LOW
        
        detected = z_score >= self.config.volume_zscore_threshold or ratio >= self.config.volume_spike_threshold
        
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
        recent_returns: List[float],
        historical_volatility: float,
        symbol: str = ""
    ) -> AnomalyResult:
        """Detect volatility spike.
        
        Args:
            recent_returns: Recent period returns
            historical_volatility: Historical volatility (standard deviation)
            symbol: Trading symbol
            
        Returns:
            AnomalyResult with detection result
        """
        if len(recent_returns) < 5:
            return AnomalyResult(
                detected=False,
                anomaly_type=AnomalyType.VOLATILITY_SPIKE,
                severity=AnomalySeverity.LOW,
                message="Insufficient return data",
                current_value=0.0,
                expected_range=(0.0, 0.0)
            )
        
        recent_vol = np.std(recent_returns, ddof=1)
        
        if historical_volatility == 0:
            return AnomalyResult(
                detected=False,
                anomaly_type=AnomalyType.VOLATILITY_SPIKE,
                severity=AnomalySeverity.LOW,
                message="No historical volatility",
                current_value=recent_vol,
                expected_range=(0.0, 0.0)
            )
        
        ratio = recent_vol / historical_volatility
        
        # Determine severity
        if ratio >= self.config.volatility_spike_threshold * 2:
            severity = AnomalySeverity.CRITICAL
        elif ratio >= self.config.volatility_spike_threshold * 1.5:
            severity = AnomalySeverity.HIGH
        elif ratio >= self.config.volatility_spike_threshold:
            severity = AnomalySeverity.MEDIUM
        else:
            severity = AnomalySeverity.LOW
        
        detected = ratio >= self.config.volatility_spike_threshold
        
        return AnomalyResult(
            detected=detected,
            anomaly_type=AnomalyType.VOLATILITY_SPIKE,
            severity=severity,
            message=f"Volatility spike detected for {symbol}: {ratio:.2f}x normal "
                    f"({recent_vol:.4f} vs {historical_volatility:.4f})",
            current_value=ratio,
            expected_range=(0.0, self.config.volatility_spike_threshold),
            z_score=None
        )
    
    def detect_price_outlier(
        self,
        current_price: float,
        historical_prices: List[float],
        symbol: str = ""
    ) -> AnomalyResult:
        """Detect price outlier using Z-score.
        
        Args:
            current_price: Current price
            historical_prices: Historical price data
            symbol: Trading symbol
            
        Returns:
            AnomalyResult with detection result
        """
        if len(historical_prices) < self.config.min_data_points:
            return AnomalyResult(
                detected=False,
                anomaly_type=AnomalyType.PRICE_OUTLIER,
                severity=AnomalySeverity.LOW,
                message=f"Insufficient price data ({len(historical_prices)} points)",
                current_value=current_price,
                expected_range=(0.0, 0.0)
            )
        
        prices_array = np.array(historical_prices)
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
        
        z_score = abs(current_price - mean_price) / std_price
        
        # Determine severity based on Z-score
        if z_score >= self.config.price_outlier_zscore * 2:
            severity = AnomalySeverity.CRITICAL
        elif z_score >= self.config.price_outlier_zscore * 1.5:
            severity = AnomalySeverity.HIGH
        elif z_score >= self.config.price_outlier_zscore:
            severity = AnomalySeverity.MEDIUM
        else:
            severity = AnomalySeverity.LOW
        
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
        historical_prices: List[float],
        historical_volumes: List[float],
        recent_returns: List[float]
    ) -> List[AnomalyResult]:
        """Run all anomaly detection checks.
        
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
        
        # Price gap
        gap_result = self.detect_price_gap(prev_close, current_price, symbol)
        if gap_result.detected:
            results.append(gap_result)
        
        # Volume spike
        volume_result = self.detect_volume_spike(
            current_volume, historical_volumes, symbol
        )
        if volume_result.detected:
            results.append(volume_result)
        
        # Volatility spike
        if len(recent_returns) >= 5 and len(historical_prices) >= 2:
            historical_vol = np.std(historical_prices[-30:]) / np.mean(historical_prices[-30:]) if len(historical_prices) >= 30 else 0.01
            vol_result = self.detect_volatility_spike(
                recent_returns, historical_vol, symbol
            )
            if vol_result.detected:
                results.append(vol_result)
        
        # Price outlier
        outlier_result = self.detect_price_outlier(
            current_price, historical_prices, symbol
        )
        if outlier_result.detected:
            results.append(outlier_result)
        
        return results
