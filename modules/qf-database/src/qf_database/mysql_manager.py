"""MySQL数据库管理器 - 使用 SQLAlchemy 2.0"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
from contextlib import contextmanager

from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Numeric, 
    Text, ForeignKey, Index, select, update, delete, and_, or_
)
from sqlalchemy.orm import declarative_base, Session, sessionmaker
from sqlalchemy.pool import QueuePool

from .models import Contract, Trade, Account

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
    """MySQL数据库管理器"""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        user: str = "root",
        password: str = "",
        database: str = "quantforge",
        pool_size: int = 10,
        max_overflow: int = 20,
        echo: bool = False
    ):
        """
        初始化MySQL管理器
        
        Args:
            host: 主机地址
            port: 端口
            user: 用户名
            password: 密码
            database: 数据库名
            pool_size: 连接池大小
            max_overflow: 最大溢出连接数
            echo: 是否输出SQL语句
        """
        self.host = host
        self.port = port
        self.database = database
        
        # 创建数据库引擎 - SQLAlchemy 2.0 语法
        self.engine = create_engine(
            f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}",
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,  # 自动检测断开连接
            pool_recycle=3600,   # 1小时后回收连接
            echo=echo
        )
        
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False
        )
        
        self._connected = False
    
    def connect(self) -> bool:
        """
        测试数据库连接
        
        Returns:
            是否连接成功
        """
        try:
            with self.engine.connect() as conn:
                conn.execute(select(1))
            self._connected = True
            return True
        except Exception as e:
            print(f"MySQL连接失败: {e}")
            self._connected = False
            return False
    
    def disconnect(self) -> None:
        """断开连接"""
        self.engine.dispose()
        self._connected = False
    
    def create_tables(self) -> None:
        """创建所有表"""
        Base.metadata.create_all(bind=self.engine)
    
    def drop_tables(self) -> None:
        """删除所有表"""
        Base.metadata.drop_all(bind=self.engine)
    
    @contextmanager
    def session_scope(self):
        """提供事务范围的session上下文管理器"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
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