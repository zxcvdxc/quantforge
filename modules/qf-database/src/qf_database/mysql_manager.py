"""MySQL数据库管理器 - 使用 SQLAlchemy 2.0

性能优化特性:
- 优化的连接池配置 (pool_size, max_overflow, pool_recycle)
- 连接池预检和自动回收
- 批量操作支持
- 异步查询支持准备
"""
from typing import Optional, List, Dict, Any, Union, Tuple
from datetime import datetime, timezone
from decimal import Decimal
from contextlib import contextmanager
import time
import logging

from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Numeric, 
    Text, ForeignKey, Index, select, update, delete, and_, or_,
    insert, func
)
from sqlalchemy.orm import declarative_base, Session, sessionmaker
from sqlalchemy.pool import QueuePool, NullPool
from sqlalchemy.exc import SQLAlchemyError, OperationalError, IntegrityError

from .models import Contract, Trade, Account

logger = logging.getLogger(__name__)
Base = declarative_base()


class ContractModel(Base):
    """合约表模型"""
    __tablename__ = 'contracts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False, index=True)
    exchange = Column(String(50), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    contract_type = Column(String(20), nullable=False)  # spot, futures, option
    base_asset = Column(String(20), nullable=False)
    quote_asset = Column(String(20), nullable=False)
    price_precision = Column(Integer, default=8)
    quantity_precision = Column(Integer, default=8)
    min_quantity = Column(Numeric(36, 18), default=Decimal('0.0001'))
    max_quantity = Column(Numeric(36, 18), default=Decimal('100000000'))
    status = Column(String(20), default='active')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_symbol_exchange', 'symbol', 'exchange', unique=True),
    )


class TradeModel(Base):
    """交易记录表模型"""
    __tablename__ = 'trades'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False, index=True)
    exchange = Column(String(50), nullable=False, index=True)
    side = Column(String(10), nullable=False)  # buy, sell
    order_type = Column(String(20), nullable=False)  # market, limit
    price = Column(Numeric(36, 18), nullable=False)
    quantity = Column(Numeric(36, 18), nullable=False)
    amount = Column(Numeric(36, 18), nullable=False)
    fee = Column(Numeric(36, 18), default=Decimal('0'))
    fee_asset = Column(String(20), default='')
    status = Column(String(20), default='pending')  # pending, filled, partial, canceled
    order_id = Column(String(100), index=True)
    trade_id = Column(String(100), index=True)
    account_id = Column(String(100), nullable=False, index=True)
    strategy_id = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_trade_account_time', 'account_id', 'created_at'),
        Index('idx_trade_symbol_time', 'symbol', 'created_at'),
    )


class AccountModel(Base):
    """账户表模型"""
    __tablename__ = 'accounts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(String(100), nullable=False, index=True)
    exchange = Column(String(50), nullable=False)
    account_type = Column(String(20), nullable=False)  # spot, margin, futures
    asset = Column(String(20), nullable=False)
    free = Column(Numeric(36, 18), default=Decimal('0'))
    locked = Column(Numeric(36, 18), default=Decimal('0'))
    total = Column(Numeric(36, 18), default=Decimal('0'))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_account_exchange_asset', 'account_id', 'exchange', 'asset', unique=True),
    )


class MySQLManager:
    """MySQL数据库管理器 - 优化版
    
    连接池优化配置:
    - pool_size: 基础连接数，默认20
    - max_overflow: 最大溢出连接数，默认30
    - pool_recycle: 连接回收时间(秒)，默认3600
    - pool_pre_ping: 连接前检测是否存活
    - pool_timeout: 获取连接超时时间(秒)，默认30
    - max_idle_time: 空闲连接最大存活时间(秒)，默认600
    
    性能特性:
    - 连接池自动管理
    - 批量插入优化
    - 查询缓存准备
    - 连接健康检查
    """
    
    # 默认连接池配置
    DEFAULT_POOL_SIZE = 20
    DEFAULT_MAX_OVERFLOW = 30
    DEFAULT_POOL_RECYCLE = 3600
    DEFAULT_POOL_TIMEOUT = 30
    DEFAULT_MAX_IDLE_TIME = 600
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        user: str = "root",
        password: str = "",
        database: str = "quantforge",
        pool_size: int = None,
        max_overflow: int = None,
        pool_recycle: int = None,
        pool_timeout: int = None,
        max_idle_time: int = None,
        echo: bool = False,
        enable_pooling: bool = True
    ):
        """
        初始化MySQL管理器
        
        Args:
            host: 主机地址
            port: 端口
            user: 用户名
            password: 密码
            database: 数据库名
            pool_size: 连接池大小 (默认20)
            max_overflow: 最大溢出连接数 (默认30)
            pool_recycle: 连接回收时间，秒 (默认3600)
            pool_timeout: 获取连接超时时间，秒 (默认30)
            max_idle_time: 空闲连接最大存活时间，秒 (默认600)
            echo: 是否输出SQL语句
            enable_pooling: 是否启用连接池 (压力测试时可禁用)
        """
        self.host = host
        self.port = port
        self.database = database
        self._connected = False
        self._connection_stats = {
            "created_at": None,
            "query_count": 0,
            "error_count": 0
        }
        
        # 使用默认配置
        pool_size = pool_size or self.DEFAULT_POOL_SIZE
        max_overflow = max_overflow or self.DEFAULT_MAX_OVERFLOW
        pool_recycle = pool_recycle or self.DEFAULT_POOL_RECYCLE
        pool_timeout = pool_timeout or self.DEFAULT_POOL_TIMEOUT
        max_idle_time = max_idle_time or self.DEFAULT_MAX_IDLE_TIME
        
        # 创建数据库引擎 - SQLAlchemy 2.0 语法
        connection_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
        
        if enable_pooling:
            self.engine = create_engine(
                connection_url,
                poolclass=QueuePool,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_pre_ping=True,  # 自动检测断开连接
                pool_recycle=pool_recycle,   # 1小时后回收连接
                pool_timeout=pool_timeout,   # 获取连接超时
                pool_use_lifo=True,  # 使用LIFO，提高缓存命中率
                echo=echo,
                # 连接参数
                connect_args={
                    "connect_timeout": 10,
                    "read_timeout": 30,
                    "write_timeout": 30,
                }
            )
        else:
            # 禁用连接池，用于压力测试
            self.engine = create_engine(
                connection_url,
                poolclass=NullPool,
                echo=echo
            )
        
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False  # 提高性能，避免重复查询
        )
        
        logger.info(f"MySQLManager initialized with pool_size={pool_size}, max_overflow={max_overflow}")
    
    def connect(self) -> bool:
        """
        测试数据库连接并获取连接池状态
        
        Returns:
            是否连接成功
        """
        try:
            start_time = time.time()
            with self.engine.connect() as conn:
                conn.execute(select(1))
            
            latency = time.time() - start_time
            self._connected = True
            self._connection_stats["created_at"] = datetime.now(timezone.utc)
            
            logger.debug(f"MySQL connection successful, latency={latency*1000:.2f}ms")
            return True
            
        except OperationalError as e:
            logger.error(f"MySQL connection failed (OperationalError): {e}")
            self._connected = False
            return False
        except SQLAlchemyError as e:
            logger.error(f"MySQL connection failed (SQLAlchemyError): {e}")
            self._connected = False
            return False
        except Exception as e:
            logger.error(f"MySQL connection failed (Unexpected): {e}")
            self._connected = False
            return False
    
    def disconnect(self) -> None:
        """断开连接并清理连接池"""
        try:
            self.engine.dispose()
            logger.info("MySQL connection pool disposed")
        except Exception as e:
            logger.warning(f"Error during disconnect: {e}")
        finally:
            self._connected = False
    
    def get_pool_status(self) -> Dict[str, Any]:
        """
        获取连接池状态
        
        Returns:
            连接池状态字典
        """
        pool = self.engine.pool
        return {
            "size": pool.size() if hasattr(pool, 'size') else -1,
            "checked_in": pool.checkedin() if hasattr(pool, 'checkedin') else -1,
            "checked_out": pool.checkedout() if hasattr(pool, 'checkedout') else -1,
            "overflow": pool.overflow() if hasattr(pool, 'overflow') else -1,
        }
    
    def health_check(self) -> Tuple[bool, float, Optional[str]]:
        """
        健康检查
        
        Returns:
            (是否健康, 延迟毫秒, 错误信息)
        """
        try:
            start_time = time.time()
            with self.engine.connect() as conn:
                conn.execute(select(1))
            latency = (time.time() - start_time) * 1000
            return True, latency, None
        except Exception as e:
            return False, 0.0, str(e)
    
    def create_tables(self) -> None:
        """创建所有表"""
        Base.metadata.create_all(bind=self.engine)
        logger.info("MySQL tables created")
    
    def drop_tables(self) -> None:
        """删除所有表"""
        Base.metadata.drop_all(bind=self.engine)
        logger.warning("MySQL tables dropped")
    
    @contextmanager
    def session_scope(self):
        """提供事务范围的session上下文管理器

        自动处理提交和回滚，确保资源释放
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Session rollback due to error: {e}")
            raise
        finally:
            session.close()
    
    @contextmanager
    def batch_session(self, batch_size: int = 1000):
        """批量操作会话上下文管理器
        
        Args:
            batch_size: 每批提交的大小
            
        Yields:
            BatchSession 对象
        """
        session = self.SessionLocal()
        batcher = _BatchSession(session, batch_size)
        try:
            yield batcher
            batcher.flush()  # 确保剩余数据提交
            session.commit()
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Batch session rollback: {e}")
            raise
        finally:
            session.close()
    
    # ==================== 合约管理 ====================
    
    def save_contract(self, contract: Contract) -> bool:
        """
        保存合约信息
        
        Args:
            contract: 合约对象
            
        Returns:
            是否保存成功
        """
        try:
            with self.session_scope() as session:
                # 检查是否已存在
                existing = session.execute(
                    select(ContractModel).where(
                        and_(
                            ContractModel.symbol == contract.symbol,
                            ContractModel.exchange == contract.exchange
                        )
                    )
                ).scalar_one_or_none()
                
                if existing:
                    # 更新
                    existing.name = contract.name
                    existing.contract_type = contract.contract_type
                    existing.base_asset = contract.base_asset
                    existing.quote_asset = contract.quote_asset
                    existing.price_precision = contract.price_precision
                    existing.quantity_precision = contract.quantity_precision
                    existing.min_quantity = contract.min_quantity
                    existing.max_quantity = contract.max_quantity
                    existing.status = contract.status
                    existing.updated_at = datetime.utcnow()
                else:
                    # 新增
                    model = ContractModel(
                        symbol=contract.symbol,
                        exchange=contract.exchange,
                        name=contract.name,
                        contract_type=contract.contract_type,
                        base_asset=contract.base_asset,
                        quote_asset=contract.quote_asset,
                        price_precision=contract.price_precision,
                        quantity_precision=contract.quantity_precision,
                        min_quantity=contract.min_quantity,
                        max_quantity=contract.max_quantity,
                        status=contract.status,
                        created_at=contract.created_at or datetime.utcnow(),
                        updated_at=contract.updated_at or datetime.utcnow()
                    )
                    session.add(model)
                
                return True
        except Exception as e:
            print(f"保存合约失败: {e}")
            return False
    
    def get_contract(self, symbol: str, exchange: str) -> Optional[Contract]:
        """
        获取合约信息
        
        Args:
            symbol: 交易对
            exchange: 交易所
            
        Returns:
            合约对象或None
        """
        try:
            with self.session_scope() as session:
                result = session.execute(
                    select(ContractModel).where(
                        and_(
                            ContractModel.symbol == symbol,
                            ContractModel.exchange == exchange
                        )
                    )
                ).scalar_one_or_none()
                
                if result:
                    return Contract(
                        symbol=result.symbol,
                        exchange=result.exchange,
                        name=result.name,
                        contract_type=result.contract_type,
                        base_asset=result.base_asset,
                        quote_asset=result.quote_asset,
                        price_precision=result.price_precision,
                        quantity_precision=result.quantity_precision,
                        min_quantity=result.min_quantity,
                        max_quantity=result.max_quantity,
                        status=result.status,
                        created_at=result.created_at,
                        updated_at=result.updated_at
                    )
                return None
        except Exception as e:
            print(f"获取合约失败: {e}")
            return None
    
    def list_contracts(
        self,
        exchange: Optional[str] = None,
        contract_type: Optional[str] = None,
        status: str = "active"
    ) -> List[Contract]:
        """
        列出合约
        
        Args:
            exchange: 交易所筛选
            contract_type: 合约类型筛选
            status: 状态筛选
            
        Returns:
            合约列表
        """
        try:
            with self.session_scope() as session:
                query = select(ContractModel)
                
                if exchange:
                    query = query.where(ContractModel.exchange == exchange)
                if contract_type:
                    query = query.where(ContractModel.contract_type == contract_type)
                if status:
                    query = query.where(ContractModel.status == status)
                
                results = session.execute(query).scalars().all()
                
                return [
                    Contract(
                        symbol=r.symbol,
                        exchange=r.exchange,
                        name=r.name,
                        contract_type=r.contract_type,
                        base_asset=r.base_asset,
                        quote_asset=r.quote_asset,
                        price_precision=r.price_precision,
                        quantity_precision=r.quantity_precision,
                        min_quantity=r.min_quantity,
                        max_quantity=r.max_quantity,
                        status=r.status,
                        created_at=r.created_at,
                        updated_at=r.updated_at
                    )
                    for r in results
                ]
        except Exception as e:
            print(f"列出合约失败: {e}")
            return []
    
    def delete_contract(self, symbol: str, exchange: str) -> bool:
        """
        删除合约
        
        Args:
            symbol: 交易对
            exchange: 交易所
            
        Returns:
            是否删除成功
        """
        try:
            with self.session_scope() as session:
                session.execute(
                    delete(ContractModel).where(
                        and_(
                            ContractModel.symbol == symbol,
                            ContractModel.exchange == exchange
                        )
                    )
                )
                return True
        except Exception as e:
            print(f"删除合约失败: {e}")
            return False
    
    # ==================== 交易记录管理 ====================
    
    def save_trade(self, trade: Trade) -> bool:
        """
        保存交易记录
        
        Args:
            trade: 交易对象
            
        Returns:
            是否保存成功
        """
        try:
            with self.session_scope() as session:
                if trade.id:
                    # 更新
                    session.execute(
                        update(TradeModel).where(TradeModel.id == trade.id).values(
                            symbol=trade.symbol,
                            exchange=trade.exchange,
                            side=trade.side,
                            order_type=trade.order_type,
                            price=trade.price,
                            quantity=trade.quantity,
                            amount=trade.amount,
                            fee=trade.fee,
                            fee_asset=trade.fee_asset,
                            status=trade.status,
                            order_id=trade.order_id,
                            trade_id=trade.trade_id,
                            account_id=trade.account_id,
                            strategy_id=trade.strategy_id,
                            updated_at=datetime.utcnow()
                        )
                    )
                else:
                    # 新增
                    model = TradeModel(
                        symbol=trade.symbol,
                        exchange=trade.exchange,
                        side=trade.side,
                        order_type=trade.order_type,
                        price=trade.price,
                        quantity=trade.quantity,
                        amount=trade.amount,
                        fee=trade.fee,
                        fee_asset=trade.fee_asset,
                        status=trade.status,
                        order_id=trade.order_id,
                        trade_id=trade.trade_id,
                        account_id=trade.account_id,
                        strategy_id=trade.strategy_id,
                        created_at=trade.created_at or datetime.utcnow(),
                        updated_at=trade.updated_at or datetime.utcnow()
                    )
                    session.add(model)
                
                return True
        except Exception as e:
            print(f"保存交易记录失败: {e}")
            return False
    
    def get_trade(self, trade_id: int) -> Optional[Trade]:
        """
        获取交易记录
        
        Args:
            trade_id: 交易ID
            
        Returns:
            交易对象或None
        """
        try:
            with self.session_scope() as session:
                result = session.execute(
                    select(TradeModel).where(TradeModel.id == trade_id)
                ).scalar_one_or_none()
                
                if result:
                    return self._trade_model_to_dataclass(result)
                return None
        except Exception as e:
            print(f"获取交易记录失败: {e}")
            return None
    
    def query_trades(
        self,
        account_id: Optional[str] = None,
        symbol: Optional[str] = None,
        exchange: Optional[str] = None,
        side: Optional[str] = None,
        status: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        strategy_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Trade]:
        """
        查询交易记录
        
        Args:
            account_id: 账户ID
            symbol: 交易对
            exchange: 交易所
            side: 买卖方向
            status: 状态
            start_time: 开始时间
            end_time: 结束时间
            strategy_id: 策略ID
            limit: 限制数量
            offset: 偏移量
            
        Returns:
            交易记录列表
        """
        try:
            with self.session_scope() as session:
                query = select(TradeModel)
                
                if account_id:
                    query = query.where(TradeModel.account_id == account_id)
                if symbol:
                    query = query.where(TradeModel.symbol == symbol)
                if exchange:
                    query = query.where(TradeModel.exchange == exchange)
                if side:
                    query = query.where(TradeModel.side == side)
                if status:
                    query = query.where(TradeModel.status == status)
                if start_time:
                    query = query.where(TradeModel.created_at >= start_time)
                if end_time:
                    query = query.where(TradeModel.created_at <= end_time)
                if strategy_id:
                    query = query.where(TradeModel.strategy_id == strategy_id)
                
                query = query.order_by(TradeModel.created_at.desc())
                query = query.limit(limit).offset(offset)
                
                results = session.execute(query).scalars().all()
                return [self._trade_model_to_dataclass(r) for r in results]
        except Exception as e:
            print(f"查询交易记录失败: {e}")
            return []
    
    def count_trades(
        self,
        account_id: Optional[str] = None,
        symbol: Optional[str] = None,
        status: Optional[str] = None
    ) -> int:
        """
        统计交易数量
        
        Args:
            account_id: 账户ID
            symbol: 交易对
            status: 状态
            
        Returns:
            交易数量
        """
        try:
            with self.session_scope() as session:
                from sqlalchemy import func
                query = select(func.count(TradeModel.id))
                
                if account_id:
                    query = query.where(TradeModel.account_id == account_id)
                if symbol:
                    query = query.where(TradeModel.symbol == symbol)
                if status:
                    query = query.where(TradeModel.status == status)
                
                return session.execute(query).scalar() or 0
        except Exception as e:
            print(f"统计交易数量失败: {e}")
            return 0
    
    def _trade_model_to_dataclass(self, model: TradeModel) -> Trade:
        """将模型转换为数据类"""
        return Trade(
            id=model.id,
            symbol=model.symbol,
            exchange=model.exchange,
            side=model.side,
            order_type=model.order_type,
            price=model.price,
            quantity=model.quantity,
            amount=model.amount,
            fee=model.fee,
            fee_asset=model.fee_asset,
            status=model.status,
            order_id=model.order_id,
            trade_id=model.trade_id,
            account_id=model.account_id,
            strategy_id=model.strategy_id,
            created_at=model.created_at,
            updated_at=model.updated_at
        )
    
    # ==================== 账户管理 ====================
    
    def save_account(self, account: Account) -> bool:
        """
        保存账户信息
        
        Args:
            account: 账户对象
            
        Returns:
            是否保存成功
        """
        try:
            with self.session_scope() as session:
                # 计算总资产
                total = account.free + account.locked
                
                # 检查是否已存在
                existing = session.execute(
                    select(AccountModel).where(
                        and_(
                            AccountModel.account_id == account.account_id,
                            AccountModel.exchange == account.exchange,
                            AccountModel.asset == account.asset
                        )
                    )
                ).scalar_one_or_none()
                
                if existing:
                    # 更新
                    existing.account_type = account.account_type
                    existing.free = account.free
                    existing.locked = account.locked
                    existing.total = total
                    existing.updated_at = datetime.utcnow()
                else:
                    # 新增
                    model = AccountModel(
                        account_id=account.account_id,
                        exchange=account.exchange,
                        account_type=account.account_type,
                        asset=account.asset,
                        free=account.free,
                        locked=account.locked,
                        total=total,
                        created_at=account.created_at or datetime.utcnow(),
                        updated_at=account.updated_at or datetime.utcnow()
                    )
                    session.add(model)
                
                return True
        except Exception as e:
            print(f"保存账户失败: {e}")
            return False
    
    def get_account(
        self,
        account_id: str,
        exchange: str,
        asset: str
    ) -> Optional[Account]:
        """
        获取账户信息
        
        Args:
            account_id: 账户ID
            exchange: 交易所
            asset: 资产
            
        Returns:
            账户对象或None
        """
        try:
            with self.session_scope() as session:
                result = session.execute(
                    select(AccountModel).where(
                        and_(
                            AccountModel.account_id == account_id,
                            AccountModel.exchange == exchange,
                            AccountModel.asset == asset
                        )
                    )
                ).scalar_one_or_none()
                
                if result:
                    return self._account_model_to_dataclass(result)
                return None
        except Exception as e:
            print(f"获取账户失败: {e}")
            return None
    
    def list_accounts(
        self,
        account_id: Optional[str] = None,
        exchange: Optional[str] = None
    ) -> List[Account]:
        """
        列出账户
        
        Args:
            account_id: 账户ID筛选
            exchange: 交易所筛选
            
        Returns:
            账户列表
        """
        try:
            with self.session_scope() as session:
                query = select(AccountModel)
                
                if account_id:
                    query = query.where(AccountModel.account_id == account_id)
                if exchange:
                    query = query.where(AccountModel.exchange == exchange)
                
                results = session.execute(query).scalars().all()
                return [self._account_model_to_dataclass(r) for r in results]
        except Exception as e:
            print(f"列出账户失败: {e}")
            return []
    
    def delete_account(
        self,
        account_id: str,
        exchange: str,
        asset: str
    ) -> bool:
        """
        删除账户
        
        Args:
            account_id: 账户ID
            exchange: 交易所
            asset: 资产
            
        Returns:
            是否删除成功
        """
        try:
            with self.session_scope() as session:
                session.execute(
                    delete(AccountModel).where(
                        and_(
                            AccountModel.account_id == account_id,
                            AccountModel.exchange == exchange,
                            AccountModel.asset == asset
                        )
                    )
                )
                return True
        except Exception as e:
            print(f"删除账户失败: {e}")
            return False
    
    def _account_model_to_dataclass(self, model: AccountModel) -> Account:
        """将模型转换为数据类"""
        return Account(
            id=model.id,
            account_id=model.account_id,
            exchange=model.exchange,
            account_type=model.account_type,
            asset=model.asset,
            free=model.free,
            locked=model.locked,
            total=model.total,
            created_at=model.created_at,
            updated_at=model.updated_at
        )
    
    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected
    
    @property
    def connection_stats(self) -> Dict[str, Any]:
        """获取连接统计信息"""
        return self._connection_stats.copy()


class _BatchSession:
    """批量操作会话辅助类"""
    
    def __init__(self, session: Session, batch_size: int = 1000):
        self.session = session
        self.batch_size = batch_size
        self._buffer: List[Any] = []
    
    def add(self, obj: Any) -> None:
        """添加对象到缓冲区"""
        self._buffer.append(obj)
        if len(self._buffer) >= self.batch_size:
            self.flush()
    
    def add_all(self, objs: List[Any]) -> None:
        """批量添加对象"""
        for obj in objs:
            self.add(obj)
    
    def flush(self) -> None:
        """刷新缓冲区到数据库"""
        if self._buffer:
            self.session.add_all(self._buffer)
            self.session.flush()
            self._buffer.clear()