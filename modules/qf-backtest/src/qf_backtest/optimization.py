"""Parameter optimization for backtesting strategies."""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from concurrent.futures import ProcessPoolExecutor, as_completed
import itertools

import numpy as np
import pandas as pd

from .engine import BacktestEngine
from .metrics import PerformanceMetrics, calculate_metrics


@dataclass
class OptimizationResult:
    """Result from parameter optimization."""
    
    params: Dict[str, Any]
    metrics: PerformanceMetrics
    score: float
    
    def __repr__(self) -> str:
        return f"OptimizationResult(params={self.params}, score={self.score:.4f})"


class GridSearchOptimizer:
    """
    Grid search optimizer for strategy parameters.
    
    Performs exhaustive search over a parameter grid to find
    optimal strategy configuration.
    """
    
    def __init__(
        self,
        engine_factory: Callable[[], BacktestEngine],
        param_grid: Dict[str, List[Any]],
        strategy_factory: Callable[..., Callable],
        scoring: str = "sharpe_ratio",
        maximize: bool = True,
        n_jobs: int = 1,
    ):
        """
        Initialize grid search optimizer.
        
        Args:
            engine_factory: Function that creates a fresh BacktestEngine
            param_grid: Dictionary of parameter names to lists of values
            strategy_factory: Function that creates strategy from parameters
            scoring: Metric to optimize (e.g., 'sharpe_ratio', 'total_return')
            maximize: True to maximize, False to minimize
            n_jobs: Number of parallel jobs (-1 for all cores)
        """
        self.engine_factory = engine_factory
        self.param_grid = param_grid
        self.strategy_factory = strategy_factory
        self.scoring = scoring
        self.maximize = maximize
        self.n_jobs = n_jobs
        
        self.results_: List[OptimizationResult] = []
        self.best_result_: Optional[OptimizationResult] = None
        self.best_params_: Optional[Dict[str, Any]] = None
        self.best_score_: Optional[float] = None
        
    def fit(
        self,
        data: pd.DataFrame,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> "GridSearchOptimizer":
        """
        Run grid search optimization.
        
        Args:
            data: Market data for backtesting
            progress_callback: Optional callback(current, total)
            
        Returns:
            self
        """
        # Generate all parameter combinations
        param_names = list(self.param_grid.keys())
        param_values = list(self.param_grid.values())
        
        combinations = list(itertools.product(*param_values))
        total = len(combinations)
        
        self.results_ = []
        
        if self.n_jobs == 1:
            # Sequential execution
            for i, values in enumerate(combinations):
                params = dict(zip(param_names, values))
                result = self._evaluate_params(params, data)
                self.results_.append(result)
                
                if progress_callback:
                    progress_callback(i + 1, total)
        else:
            # Parallel execution
            n_workers = self.n_jobs if self.n_jobs > 0 else None
            
            with ProcessPoolExecutor(max_workers=n_workers) as executor:
                futures = {
                    executor.submit(
                        self._evaluate_params,
                        dict(zip(param_names, values)),
                        data,
                    ): values
                    for values in combinations
                }
                
                completed = 0
                for future in as_completed(futures):
                    result = future.result()
                    self.results_.append(result)
                    completed += 1
                    
                    if progress_callback:
                        progress_callback(completed, total)
        
        # Find best result
        self._select_best()
        
        return self
    
    def _evaluate_params(
        self,
        params: Dict[str, Any],
        data: pd.DataFrame,
    ) -> OptimizationResult:
        """Evaluate a single parameter set."""
        # Create fresh engine and strategy
        engine = self.engine_factory()
        strategy = self.strategy_factory(**params)
        
        # Run backtest
        equity_curve = engine.run(data, strategy)
        trades = engine.get_trades()
        
        # Calculate metrics
        metrics = calculate_metrics(
            equity_curve,
            trades,
            initial_capital=engine.initial_capital,
        )
        
        # Calculate score
        score = getattr(metrics, self.scoring, 0.0)
        if not isinstance(score, (int, float)):
            score = 0.0
            
        return OptimizationResult(params=params, metrics=metrics, score=score)
    
    def _select_best(self) -> None:
        """Select best result based on scoring metric."""
        if not self.results_:
            return
            
        if self.maximize:
            self.best_result_ = max(self.results_, key=lambda r: r.score)
        else:
            self.best_result_ = min(self.results_, key=lambda r: r.score)
            
        self.best_params_ = self.best_result_.params
        self.best_score_ = self.best_result_.score
        
    def get_results_df(self) -> pd.DataFrame:
        """Get all results as a DataFrame."""
        records = []
        for result in self.results_:
            record = {
                **result.params,
                "score": result.score,
                **result.metrics.to_dict(),
            }
            records.append(record)
        return pd.DataFrame(records)
    
    def top_results(self, n: int = 5) -> List[OptimizationResult]:
        """Get top N results."""
        sorted_results = sorted(
            self.results_,
            key=lambda r: r.score,
            reverse=self.maximize,
        )
        return sorted_results[:n]


def optimize_parameters(
    data: pd.DataFrame,
    strategy_factory: Callable[..., Callable],
    param_grid: Dict[str, List[Any]],
    initial_capital: float = 100000.0,
    scoring: str = "sharpe_ratio",
    maximize: bool = True,
    n_jobs: int = 1,
    slippage_model: Optional[Any] = None,
    commission_model: Optional[Any] = None,
) -> Tuple[Dict[str, Any], PerformanceMetrics]:
    """
    Convenience function for parameter optimization.
    
    Args:
        data: Market data
        strategy_factory: Function creating strategy from parameters
        param_grid: Parameter grid to search
        initial_capital: Starting capital
        scoring: Metric to optimize
        maximize: True to maximize
        n_jobs: Parallel jobs
        slippage_model: Optional slippage model
        commission_model: Optional commission model
        
    Returns:
        (best_params, best_metrics)
    """
    from .slippage import NoSlippage
    from .commission import NoCommission
    
    if slippage_model is None:
        slippage_model = NoSlippage()
    if commission_model is None:
        commission_model = NoCommission()
        
    def engine_factory() -> BacktestEngine:
        return BacktestEngine(
            initial_capital=initial_capital,
            slippage_model=slippage_model,
            commission_model=commission_model,
        )
        
    optimizer = GridSearchOptimizer(
        engine_factory=engine_factory,
        param_grid=param_grid,
        strategy_factory=strategy_factory,
        scoring=scoring,
        maximize=maximize,
        n_jobs=n_jobs,
    )
    
    optimizer.fit(data)
    
    if optimizer.best_result_ is None:
        return {}, PerformanceMetrics()
        
    return optimizer.best_params_, optimizer.best_result_.metrics


class WalkForwardOptimizer:
    """
    Walk-forward optimization for strategy parameters.
    
    Uses in-sample periods for optimization and out-of-sample
    periods for validation to reduce overfitting.
    """
    
    def __init__(
        self,
        engine_factory: Callable[[], BacktestEngine],
        param_grid: Dict[str, List[Any]],
        strategy_factory: Callable[..., Callable],
        train_size: int = 252,  # Days
        test_size: int = 63,    # Days
        scoring: str = "sharpe_ratio",
    ):
        """
        Initialize walk-forward optimizer.
        
        Args:
            engine_factory: Function creating BacktestEngine
            param_grid: Parameter grid
            strategy_factory: Function creating strategy
            train_size: Size of in-sample period
            test_size: Size of out-of-sample period
            scoring: Metric to optimize
        """
        self.engine_factory = engine_factory
        self.param_grid = param_grid
        self.strategy_factory = strategy_factory
        self.train_size = train_size
        self.test_size = test_size
        self.scoring = scoring
        
        self.results_: List[Dict[str, Any]] = []
        
    def fit(self, data: pd.DataFrame) -> "WalkForwardOptimizer":
        """Run walk-forward optimization."""
        # Sort data by timestamp
        data = data.sort_values("timestamp").reset_index(drop=True)
        
        n_bars = len(data)
        start = 0
        
        while start + self.train_size + self.test_size <= n_bars:
            # Split data
            train_end = start + self.train_size
            test_end = train_end + self.test_size
            
            train_data = data.iloc[start:train_end]
            test_data = data.iloc[train_end:test_end]
            
            # Optimize on training data
            optimizer = GridSearchOptimizer(
                engine_factory=self.engine_factory,
                param_grid=self.param_grid,
                strategy_factory=self.strategy_factory,
                scoring=self.scoring,
            )
            optimizer.fit(train_data)
            
            if optimizer.best_params_ is None:
                start += self.test_size
                continue
            
            # Test on out-of-sample data
            engine = self.engine_factory()
            strategy = self.strategy_factory(**optimizer.best_params_)
            
            equity_curve = engine.run(test_data, strategy)
            trades = engine.get_trades()
            
            metrics = calculate_metrics(
                equity_curve,
                trades,
                initial_capital=engine.initial_capital,
            )
            
            self.results_.append({
                "train_start": train_data["timestamp"].iloc[0],
                "train_end": train_data["timestamp"].iloc[-1],
                "test_start": test_data["timestamp"].iloc[0],
                "test_end": test_data["timestamp"].iloc[-1],
                "best_params": optimizer.best_params_,
                "train_score": optimizer.best_score_,
                "test_metrics": metrics,
            })
            
            start += self.test_size
            
        return self
    
    def get_avg_test_metrics(self) -> PerformanceMetrics:
        """Get average metrics across all test periods."""
        if not self.results_:
            return PerformanceMetrics()
            
        # Aggregate metrics
        metrics_list = [r["test_metrics"] for r in self.results_]
        
        avg_metrics = PerformanceMetrics()
        for attr in ["total_return", "sharpe_ratio", "max_drawdown", "win_rate"]:
            values = [getattr(m, attr) for m in metrics_list]
            setattr(avg_metrics, attr, np.mean(values))
            
        return avg_metrics
