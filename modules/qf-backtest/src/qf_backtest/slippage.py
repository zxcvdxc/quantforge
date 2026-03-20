"""Slippage models for order execution simulation."""

from abc import ABC, abstractmethod
from typing import Any, Optional
import random

from .engine import Order, MarketDataEvent, OrderSide


class SlippageModel(ABC):
    """Abstract base class for slippage models."""
    
    @abstractmethod
    def calculate_slippage(
        self,
        order: Order,
        base_price: float,
        market_data: MarketDataEvent,
    ) -> float:
        """
        Calculate slippage amount.
        
        Args:
            order: The order being executed
            base_price: The expected execution price
            market_data: Current market data
            
        Returns:
            Slippage amount (positive value)
        """
        pass


class NoSlippage(SlippageModel):
    """No slippage - perfect execution at expected price."""
    
    def calculate_slippage(
        self,
        order: Order,
        base_price: float,
        market_data: MarketDataEvent,
    ) -> float:
        """Return zero slippage."""
        return 0.0


class PercentageSlippage(SlippageModel):
    """
    Percentage-based slippage model.
    
    Slippage is calculated as a percentage of the base price.
    Can optionally add random noise for more realistic simulation.
    """
    
    def __init__(
        self,
        slippage_pct: float = 0.001,  # 0.1% default
        randomize: bool = False,
        max_deviation: float = 0.5,  # Max 50% deviation from base slippage
    ):
        """
        Initialize percentage slippage model.
        
        Args:
            slippage_pct: Slippage percentage (e.g., 0.001 = 0.1%)
            randomize: Whether to add random variation
            max_deviation: Max deviation multiplier when randomizing
        """
        self.slippage_pct = slippage_pct
        self.randomize = randomize
        self.max_deviation = max_deviation
        
    def calculate_slippage(
        self,
        order: Order,
        base_price: float,
        market_data: MarketDataEvent,
    ) -> float:
        """Calculate percentage slippage."""
        base_slippage = base_price * self.slippage_pct
        
        if self.randomize:
            # Add random noise between -deviation and +deviation
            noise = random.uniform(-self.max_deviation, self.max_deviation)
            base_slippage *= (1 + noise)
            
        return max(0.0, base_slippage)


class FixedSlippage(SlippageModel):
    """
    Fixed amount slippage model.
    
    Applies a fixed price amount as slippage regardless of price level.
    """
    
    def __init__(
        self,
        fixed_amount: float,
        randomize: bool = False,
        max_deviation: float = 0.5,
    ):
        """
        Initialize fixed slippage model.
        
        Args:
            fixed_amount: Fixed slippage amount in price terms
            randomize: Whether to add random variation
            max_deviation: Max deviation multiplier when randomizing
        """
        self.fixed_amount = fixed_amount
        self.randomize = randomize
        self.max_deviation = max_deviation
        
    def calculate_slippage(
        self,
        order: Order,
        base_price: float,
        market_data: MarketDataEvent,
    ) -> float:
        """Calculate fixed slippage."""
        slippage = self.fixed_amount
        
        if self.randomize:
            noise = random.uniform(-self.max_deviation, self.max_deviation)
            slippage *= (1 + noise)
            
        return max(0.0, slippage)


class VolumeBasedSlippage(SlippageModel):
    """
    Volume-based slippage model.
    
    Slippage increases with order size relative to market volume.
    """
    
    def __init__(
        self,
        base_slippage_pct: float = 0.001,
        volume_factor: float = 1.0,
        max_slippage_pct: float = 0.1,  # Max 10% slippage
    ):
        """
        Initialize volume-based slippage model.
        
        Args:
            base_slippage_pct: Base slippage percentage
            volume_factor: Multiplier for volume impact
            max_slippage_pct: Maximum slippage percentage
        """
        self.base_slippage_pct = base_slippage_pct
        self.volume_factor = volume_factor
        self.max_slippage_pct = max_slippage_pct
        
    def calculate_slippage(
        self,
        order: Order,
        base_price: float,
        market_data: MarketDataEvent,
    ) -> float:
        """Calculate volume-adjusted slippage."""
        if market_data.volume == 0:
            volume_ratio = 0.0
        else:
            volume_ratio = order.quantity / market_data.volume
            
        # Slippage increases with volume ratio
        slippage_pct = self.base_slippage_pct * (
            1 + self.volume_factor * volume_ratio
        )
        
        # Cap at maximum
        slippage_pct = min(slippage_pct, self.max_slippage_pct)
        
        return base_price * slippage_pct


class VolatilityBasedSlippage(SlippageModel):
    """
    Volatility-based slippage model.
    
    Slippage increases with intraday volatility (high-low range).
    """
    
    def __init__(
        self,
        base_slippage_pct: float = 0.0005,
        volatility_factor: float = 2.0,
        min_slippage_pct: float = 0.0001,
        max_slippage_pct: float = 0.05,
    ):
        """
        Initialize volatility-based slippage model.
        
        Args:
            base_slippage_pct: Base slippage percentage
            volatility_factor: Multiplier for volatility impact
            min_slippage_pct: Minimum slippage percentage
            max_slippage_pct: Maximum slippage percentage
        """
        self.base_slippage_pct = base_slippage_pct
        self.volatility_factor = volatility_factor
        self.min_slippage_pct = min_slippage_pct
        self.max_slippage_pct = max_slippage_pct
        
    def calculate_slippage(
        self,
        order: Order,
        base_price: float,
        market_data: MarketDataEvent,
    ) -> float:
        """Calculate volatility-adjusted slippage."""
        # Calculate intraday volatility
        price_range = market_data.high - market_data.low
        if base_price > 0:
            volatility = price_range / base_price
        else:
            volatility = 0.0
            
        # Slippage increases with volatility
        slippage_pct = self.base_slippage_pct * (
            1 + self.volatility_factor * volatility
        )
        
        # Apply bounds
        slippage_pct = max(self.min_slippage_pct, slippage_pct)
        slippage_pct = min(self.max_slippage_pct, slippage_pct)
        
        return base_price * slippage_pct
