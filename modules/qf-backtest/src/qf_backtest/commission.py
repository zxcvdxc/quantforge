"""Commission models for trading fee calculation."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Optional

from .engine import Order, OrderSide


class CommissionModel(ABC):
    """Abstract base class for commission models."""
    
    @abstractmethod
    def calculate_commission(self, order: Order, fill_price: float) -> float:
        """
        Calculate commission for an order fill.
        
        Args:
            order: The filled order
            fill_price: The execution price
            
        Returns:
            Commission amount (always positive)
        """
        pass


@dataclass
class PercentageCommission(CommissionModel):
    """
    Percentage-based commission model.
    
    Commission is calculated as a percentage of trade value.
    Supports different rates for different symbols.
    """
    
    default_rate: float = 0.001  # 0.1% default
    symbol_rates: Dict[str, float] = field(default_factory=dict)
    min_commission: float = 0.0
    max_commission_pct: Optional[float] = None  # As decimal, e.g., 0.01 = 1%
    
    def __init__(
        self,
        rate: float = 0.001,
        symbol_rates: Optional[Dict[str, float]] = None,
        min_commission: float = 0.0,
        max_commission_pct: Optional[float] = None,
    ):
        """
        Initialize percentage commission model.
        
        Args:
            rate: Default commission rate (e.g., 0.001 = 0.1%)
            symbol_rates: Per-symbol commission rates
            min_commission: Minimum commission per trade
            max_commission_pct: Maximum commission as % of trade value
        """
        self.default_rate = rate
        self.symbol_rates = symbol_rates or {}
        self.min_commission = min_commission
        self.max_commission_pct = max_commission_pct
        
    def calculate_commission(self, order: Order, fill_price: float) -> float:
        """Calculate percentage commission."""
        # Get rate for symbol or use default
        rate = self.symbol_rates.get(order.symbol, self.default_rate)
        
        # Calculate commission
        trade_value = order.quantity * fill_price
        commission = trade_value * rate
        
        # Apply minimum
        commission = max(commission, self.min_commission)
        
        # Apply maximum if specified
        if self.max_commission_pct is not None:
            max_commission = trade_value * self.max_commission_pct
            commission = min(commission, max_commission)
            
        return commission


@dataclass
class FixedCommission(CommissionModel):
    """
    Fixed amount commission model.
    
    Commission is a fixed amount per trade, regardless of size.
    Supports different amounts for different symbols.
    """
    
    default_amount: float = 5.0
    symbol_amounts: Dict[str, float] = field(default_factory=dict)
    per_share: bool = False  # If True, amount is per share/contract
    
    def __init__(
        self,
        amount: float = 5.0,
        symbol_amounts: Optional[Dict[str, float]] = None,
        per_share: bool = False,
    ):
        """
        Initialize fixed commission model.
        
        Args:
            amount: Default fixed commission amount
            symbol_amounts: Per-symbol commission amounts
            per_share: If True, multiply by quantity
        """
        self.default_amount = amount
        self.symbol_amounts = symbol_amounts or {}
        self.per_share = per_share
        
    def calculate_commission(self, order: Order, fill_price: float) -> float:
        """Calculate fixed commission."""
        # Get amount for symbol or use default
        amount = self.symbol_amounts.get(order.symbol, self.default_amount)
        
        if self.per_share:
            return amount * order.quantity
        return amount


@dataclass
class TieredCommission(CommissionModel):
    """
    Tiered commission model.
    
    Commission rate decreases as trade volume increases.
    """
    
    tiers: list = field(default_factory=lambda: [
        (0, 0.001),          # 0.1% for trades up to tier 1
        (10000, 0.0008),     # 0.08% for next tier
        (50000, 0.0005),     # 0.05% for next tier
    ])
    min_commission: float = 1.0
    
    def __init__(
        self,
        tiers: Optional[list] = None,
        min_commission: float = 1.0,
    ):
        """
        Initialize tiered commission model.
        
        Args:
            tiers: List of (threshold, rate) tuples, sorted by threshold
            min_commission: Minimum commission per trade
        """
        self.tiers = tiers or [(0, 0.001), (10000, 0.0008), (50000, 0.0005)]
        self.min_commission = min_commission
        
    def calculate_commission(self, order: Order, fill_price: float) -> float:
        """Calculate tiered commission."""
        trade_value = order.quantity * fill_price
        
        # Find applicable rate
        rate = self.tiers[0][1]
        for threshold, tier_rate in self.tiers:
            if trade_value >= threshold:
                rate = tier_rate
            else:
                break
                
        commission = trade_value * rate
        return max(commission, self.min_commission)


@dataclass
class HybridCommission(CommissionModel):
    """
    Hybrid commission model combining fixed and percentage.
    
    Commission = max(fixed_amount, percentage_of_value)
    """
    
    fixed_amount: float = 5.0
    percentage_rate: float = 0.001
    min_commission: float = 0.0
    
    def __init__(
        self,
        fixed_amount: float = 5.0,
        percentage_rate: float = 0.001,
        min_commission: float = 0.0,
    ):
        """
        Initialize hybrid commission model.
        
        Args:
            fixed_amount: Fixed commission component
            percentage_rate: Percentage commission rate
            min_commission: Minimum total commission
        """
        self.fixed_amount = fixed_amount
        self.percentage_rate = percentage_rate
        self.min_commission = min_commission
        
    def calculate_commission(self, order: Order, fill_price: float) -> float:
        """Calculate hybrid commission (max of fixed and percentage)."""
        trade_value = order.quantity * fill_price
        percentage_commission = trade_value * self.percentage_rate
        
        commission = max(self.fixed_amount, percentage_commission)
        return max(commission, self.min_commission)


class NoCommission(CommissionModel):
    """No commission - zero fees."""
    
    def calculate_commission(self, order: Order, fill_price: float) -> float:
        """Return zero commission."""
        return 0.0
