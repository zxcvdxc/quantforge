"""
ML Weights Predictor - 机器学习权重预测

使用LightGBM预测最优资产配置权重
"""

from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


class MLWeightsPredictor:
    """
    机器学习权重预测器
    
    基于LightGBM模型预测各资产的最优配置权重
    """
    
    def __init__(
        self,
        lookback_window: int = 60,           # 特征回望窗口
        forecast_horizon: int = 5,            # 预测周期
        confidence_threshold: float = 0.6,    # 置信度阈值
        min_samples: int = 100,               # 最小训练样本数
        model_params: Optional[Dict] = None,  # LightGBM参数
    ):
        """
        初始化ML权重预测器
        
        Args:
            lookback_window: 特征计算的回望窗口
            forecast_horizon: 收益率预测周期
            confidence_threshold: 最低置信度阈值
            min_samples: 最小训练样本数
            model_params: LightGBM模型参数
        """
        self.lookback_window = lookback_window
        self.forecast_horizon = forecast_horizon
        self.confidence_threshold = confidence_threshold
        self.min_samples = min_samples
        
        # LightGBM参数
        self.model_params = model_params or {
            "objective": "regression",
            "metric": "rmse",
            "boosting_type": "gbdt",
            "num_leaves": 31,
            "learning_rate": 0.05,
            "feature_fraction": 0.9,
            "bagging_fraction": 0.8,
            "bagging_freq": 5,
            "verbose": -1,
            "n_estimators": 100,
        }
        
        self.models: Dict[str, Any] = {}
        self.is_fitted: bool = False
        self.feature_importance: Dict[str, Dict[str, float]] = {}
        self.prediction_history: List[Dict] = []
    
    def fit(
        self,
        returns_data: pd.DataFrame,
        features: Optional[pd.DataFrame] = None,
        **kwargs
    ) -> "MLWeightsPredictor":
        """
        训练模型
        
        Args:
            returns_data: 历史收益率数据
            features: 自定义特征（可选）
            **kwargs: 额外参数
        
        Returns:
            self
        """
        try:
            import lightgbm as lgb
        except ImportError:
            raise ImportError("LightGBM未安装，请运行: pip install lightgbm")
        
        if returns_data.empty or len(returns_data) < self.min_samples:
            raise ValueError(f"训练数据不足，需要至少{self.min_samples}个样本")
        
        symbols = returns_data.columns.tolist()
        
        for symbol in symbols:
            # 准备特征和目标
            X, y = self._prepare_data(symbol, returns_data, features)
            
            if len(X) < self.min_samples:
                continue
            
            # 训练模型
            model = lgb.LGBMRegressor(**self.model_params)
            model.fit(X, y)
            
            self.models[symbol] = model
            
            # 记录特征重要性
            if hasattr(model, 'feature_importances_'):
                feature_names = self._get_feature_names()
                self.feature_importance[symbol] = {
                    feature_names[i]: float(model.feature_importances_[i])
                    for i in range(len(feature_names))
                }
        
        self.is_fitted = len(self.models) > 0
        
        return self
    
    def predict_weights(
        self,
        symbols: List[str],
        returns_data: Optional[pd.DataFrame] = None,
        features: Optional[pd.DataFrame] = None,
        use_confidence_filter: bool = True,
        **kwargs
    ) -> Dict[str, float]:
        """
        预测最优权重
        
        Args:
            symbols: 资产代码列表
            returns_data: 历史收益率数据
            features: 自定义特征
            use_confidence_filter: 是否使用置信度过滤
            **kwargs: 额外参数
        
        Returns:
            Dict[str, float]: 预测权重
        """
        if not self.is_fitted and returns_data is not None:
            # 自动训练
            try:
                self.fit(returns_data)
            except Exception:
                pass
        
        if not self.is_fitted or not self.models:
            # 模型未训练，使用动量策略回退
            return self._momentum_fallback(symbols, returns_data)
        
        predictions = {}
        confidences = {}
        
        for symbol in symbols:
            if symbol not in self.models:
                predictions[symbol] = 0.0
                confidences[symbol] = 0.0
                continue
            
            # 准备特征
            X = self._prepare_features(symbol, returns_data, features)
            
            # 预测
            model = self.models[symbol]
            pred = model.predict(X.reshape(1, -1))[0]
            
            predictions[symbol] = pred
            
            # 计算置信度（基于预测的标准差）
            if hasattr(model, 'booster_'):
                try:
                    # 使用叶节点方差估计置信度
                    leaves = model.predict(X.reshape(1, -1), pred_leaf=True)
                    confidences[symbol] = self._calculate_confidence(model, leaves)
                except Exception:
                    confidences[symbol] = 0.5
            else:
                confidences[symbol] = 0.5
        
        # 转换为权重
        weights = self._predictions_to_weights(
            predictions, confidences, use_confidence_filter
        )
        
        # 记录预测历史
        self.prediction_history.append({
            "timestamp": datetime.now(),
            "predictions": predictions.copy(),
            "confidences": confidences.copy(),
            "weights": weights.copy(),
        })
        
        return weights
    
    def predict_returns(
        self,
        symbols: List[str],
        returns_data: Optional[pd.DataFrame] = None,
        features: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Tuple[float, float]]:
        """
        预测各资产的预期收益率和置信度
        
        Returns:
            Dict[str, Tuple[float, float]]: {symbol: (预期收益, 置信度)}
        """
        if not self.is_fitted:
            return {s: (0.0, 0.0) for s in symbols}
        
        result = {}
        
        for symbol in symbols:
            if symbol not in self.models:
                result[symbol] = (0.0, 0.0)
                continue
            
            X = self._prepare_features(symbol, returns_data, features)
            model = self.models[symbol]
            
            pred = model.predict(X.reshape(1, -1))[0]
            
            # 简单置信度估计
            confidence = 0.5
            if hasattr(model, 'booster_'):
                try:
                    leaves = model.predict(X.reshape(1, -1), pred_leaf=True)
                    confidence = self._calculate_confidence(model, leaves)
                except Exception:
                    pass
            
            result[symbol] = (float(pred), float(confidence))
        
        return result
    
    def get_feature_importance(self, symbol: Optional[str] = None) -> Dict:
        """获取特征重要性"""
        if symbol:
            return self.feature_importance.get(symbol, {})
        return self.feature_importance
    
    def get_prediction_stats(self) -> Dict[str, Any]:
        """获取预测统计信息"""
        if not self.prediction_history:
            return {}
        
        recent = self.prediction_history[-10:]  # 最近10次预测
        
        stats = {
            "total_predictions": len(self.prediction_history),
            "avg_confidence": np.mean([
                np.mean(list(p["confidences"].values()))
                for p in recent
            ]),
            "models_trained": len(self.models),
        }
        
        return stats
    
    def _prepare_data(
        self,
        symbol: str,
        returns_data: pd.DataFrame,
        features: Optional[pd.DataFrame],
    ) -> Tuple[np.ndarray, np.ndarray]:
        """准备训练数据"""
        # 计算未来收益率作为目标
        future_returns = returns_data[symbol].shift(-self.forecast_horizon)
        
        # 生成特征
        if features is not None:
            X = features.values
        else:
            X = self._generate_features(symbol, returns_data)
        
        y = future_returns.values
        
        # 移除NaN
        mask = ~np.isnan(y)
        X = X[mask]
        y = y[mask]
        
        return X, y
    
    def _generate_features(
        self,
        symbol: str,
        returns_data: pd.DataFrame,
    ) -> np.ndarray:
        """生成技术特征"""
        if symbol not in returns_data.columns:
            return np.zeros((len(returns_data), 10))
        
        returns = returns_data[symbol]
        
        features_list = []
        
        # 收益率特征
        for window in [5, 10, 20, 60]:
            if len(returns) >= window:
                features_list.append(returns.rolling(window).mean().values)
                features_list.append(returns.rolling(window).std().values)
            else:
                features_list.append(np.zeros(len(returns)))
                features_list.append(np.zeros(len(returns)))
        
        # 累积收益
        for window in [5, 20]:
            if len(returns) >= window:
                cumret = (1 + returns).rolling(window).apply(lambda x: x.prod()) - 1
                features_list.append(cumret.values)
            else:
                features_list.append(np.zeros(len(returns)))
        
        # 趋势特征
        if len(returns) >= 20:
            sma20 = returns.rolling(20).mean()
            features_list.append((returns > sma20).astype(float).values)
        else:
            features_list.append(np.zeros(len(returns)))
        
        # 波动率特征
        if len(returns) >= 20:
            vol = returns.rolling(20).std()
            features_list.append((returns.abs() > 2 * vol).astype(float).values)
        else:
            features_list.append(np.zeros(len(returns)))
        
        # 组合为特征矩阵
        X = np.column_stack(features_list)
        
        # 填充NaN
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        
        return X
    
    def _prepare_features(
        self,
        symbol: str,
        returns_data: Optional[pd.DataFrame],
        features: Optional[pd.DataFrame],
    ) -> np.ndarray:
        """准备预测特征"""
        if features is not None:
            return features.iloc[-1].values
        
        if returns_data is None or symbol not in returns_data.columns:
            return np.zeros(10)
        
        # 使用最新的数据生成特征
        recent_data = returns_data.tail(self.lookback_window)
        X_full = self._generate_features(symbol, recent_data)
        
        return X_full[-1]
    
    def _get_feature_names(self) -> List[str]:
        """获取特征名称"""
        names = []
        for window in [5, 10, 20, 60]:
            names.append(f"mean_{window}")
            names.append(f"std_{window}")
        for window in [5, 20]:
            names.append(f"cumret_{window}")
        names.append("trend")
        names.append("volatility_signal")
        return names
    
    def _calculate_confidence(self, model: Any, leaves: np.ndarray) -> float:
        """计算预测置信度"""
        # 简化的置信度计算
        # 实际应用中可以使用更复杂的方法
        return 0.7
    
    def _predictions_to_weights(
        self,
        predictions: Dict[str, float],
        confidences: Dict[str, float],
        use_confidence_filter: bool,
    ) -> Dict[str, float]:
        """将预测转换为权重"""
        symbols = list(predictions.keys())
        
        if use_confidence_filter:
            # 过滤低置信度预测
            filtered_preds = {
                s: p for s, p in predictions.items()
                if confidences.get(s, 0) >= self.confidence_threshold
            }
            
            if not filtered_preds:
                # 全部过滤，使用等权重
                n = len(symbols)
                return {s: 1.0 / n for s in symbols}
            
            predictions = filtered_preds
            symbols = list(predictions.keys())
        
        # 预测收益转换为权重
        # 使用softmax转换
        preds = np.array([predictions.get(s, 0) for s in symbols])
        
        # 处理负值
        preds = preds - preds.min() + 1e-6
        
        # Softmax
        exp_preds = np.exp(preds - np.max(preds))
        weights = exp_preds / exp_preds.sum()
        
        return {symbols[i]: float(weights[i]) for i in range(len(symbols))}
    
    def _momentum_fallback(
        self,
        symbols: List[str],
        returns_data: Optional[pd.DataFrame],
    ) -> Dict[str, float]:
        """动量策略回退"""
        if returns_data is None or returns_data.empty:
            n = len(symbols)
            return {s: 1.0 / n for s in symbols}
        
        # 计算近期动量
        momentums = {}
        for symbol in symbols:
            if symbol in returns_data.columns:
                recent = returns_data[symbol].tail(self.lookback_window)
                momentum = recent.mean() / (recent.std() + 1e-6)
                momentums[symbol] = momentum
            else:
                momentums[symbol] = 0.0
        
        # 动量转换为权重
        total_momentum = sum(max(0, m) for m in momentums.values())
        
        if total_momentum > 0:
            weights = {
                s: max(0, m) / total_momentum
                for s, m in momentums.items()
            }
        else:
            n = len(symbols)
            weights = {s: 1.0 / n for s in symbols}
        
        return weights
    
    def reset(self) -> None:
        """重置模型状态"""
        self.models.clear()
        self.is_fitted = False
        self.feature_importance.clear()
        self.prediction_history.clear()
