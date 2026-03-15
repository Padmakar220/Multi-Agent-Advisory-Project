"""Portfolio data models for the Multi-Agent Advisory AI System."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Dict, Optional
from decimal import Decimal


@dataclass
class Holding:
    """Represents a single security holding in a portfolio."""
    
    ticker: str
    quantity: int
    cost_basis: float
    current_price: float
    purchase_date: str  # ISO 8601 format
    
    def __post_init__(self):
        """Validate holding data."""
        if self.quantity < 0:
            raise ValueError(f"Quantity must be non-negative, got {self.quantity}")
        if self.cost_basis < 0:
            raise ValueError(f"Cost basis must be non-negative, got {self.cost_basis}")
        if self.current_price < 0:
            raise ValueError(f"Current price must be non-negative, got {self.current_price}")
        if not self.ticker:
            raise ValueError("Ticker symbol cannot be empty")
    
    @property
    def market_value(self) -> float:
        """Calculate current market value of the holding."""
        return self.quantity * self.current_price
    
    @property
    def unrealized_gain_loss(self) -> float:
        """Calculate unrealized gain or loss."""
        return self.market_value - (self.quantity * self.cost_basis)
    
    def to_dynamodb(self) -> Dict:
        """Convert to DynamoDB item format."""
        return {
            "ticker": self.ticker,
            "quantity": self.quantity,
            "cost_basis": Decimal(str(self.cost_basis)),
            "current_price": Decimal(str(self.current_price)),
            "purchase_date": self.purchase_date
        }
    
    @classmethod
    def from_dynamodb(cls, item: Dict) -> 'Holding':
        """Create Holding from DynamoDB item."""
        return cls(
            ticker=item["ticker"],
            quantity=int(item["quantity"]),
            cost_basis=float(item["cost_basis"]),
            current_price=float(item["current_price"]),
            purchase_date=item["purchase_date"]
        )


@dataclass
class Portfolio:
    """Represents a user's investment portfolio."""
    
    user_id: str
    portfolio_id: str
    portfolio_name: str
    target_allocation: Dict[str, float]
    holdings: List[Holding] = field(default_factory=list)
    total_value: float = 0.0
    risk_tolerance: str = "moderate"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def __post_init__(self):
        """Validate portfolio data."""
        if not self.user_id:
            raise ValueError("User ID cannot be empty")
        if not self.portfolio_id:
            raise ValueError("Portfolio ID cannot be empty")
        if self.risk_tolerance not in ["conservative", "moderate", "aggressive"]:
            raise ValueError(f"Invalid risk tolerance: {self.risk_tolerance}")
        
        # Validate target allocation sums to 1.0
        if self.target_allocation:
            total = sum(self.target_allocation.values())
            if abs(total - 1.0) > 0.01:
                raise ValueError(f"Target allocation must sum to 1.0, got {total}")
        
        # Calculate total value if not provided
        if self.total_value == 0.0 and self.holdings:
            self.total_value = sum(h.market_value for h in self.holdings)
    
    def get_allocation(self, asset_class: str) -> float:
        """Get current allocation percentage for an asset class."""
        if self.total_value == 0:
            return 0.0
        
        # This is simplified - in reality, you'd map tickers to asset classes
        # For now, return 0.0 as placeholder
        return 0.0
    
    def to_dynamodb(self) -> Dict:
        """Convert to DynamoDB item format."""
        return {
            "user_id": self.user_id,
            "portfolio_id": self.portfolio_id,
            "portfolio_name": self.portfolio_name,
            "target_allocation": {k: Decimal(str(v)) for k, v in self.target_allocation.items()},
            "holdings": [h.to_dynamodb() for h in self.holdings],
            "total_value": Decimal(str(self.total_value)),
            "risk_tolerance": self.risk_tolerance,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
    
    @classmethod
    def from_dynamodb(cls, item: Dict) -> 'Portfolio':
        """Create Portfolio from DynamoDB item."""
        return cls(
            user_id=item["user_id"],
            portfolio_id=item["portfolio_id"],
            portfolio_name=item["portfolio_name"],
            target_allocation={k: float(v) for k, v in item["target_allocation"].items()},
            holdings=[Holding.from_dynamodb(h) for h in item.get("holdings", [])],
            total_value=float(item["total_value"]),
            risk_tolerance=item["risk_tolerance"],
            created_at=item["created_at"],
            updated_at=item["updated_at"]
        )


@dataclass
class Transaction:
    """Represents a portfolio transaction."""
    
    user_id: str
    timestamp: str
    transaction_id: str
    portfolio_id: str
    action: str  # "buy" or "sell"
    ticker: str
    quantity: int
    price: float
    commission: float = 0.0
    total_cost: float = 0.0
    execution_status: str = "pending"
    order_type: str = "market"
    initiated_by: str = "user"
    
    def __post_init__(self):
        """Validate transaction data."""
        if self.action not in ["buy", "sell"]:
            raise ValueError(f"Action must be 'buy' or 'sell', got {self.action}")
        if self.quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {self.quantity}")
        if self.price < 0:
            raise ValueError(f"Price must be non-negative, got {self.price}")
        if self.execution_status not in ["pending", "completed", "failed", "cancelled"]:
            raise ValueError(f"Invalid execution status: {self.execution_status}")
        
        # Calculate total cost if not provided
        if self.total_cost == 0.0:
            self.total_cost = (self.quantity * self.price) + self.commission
    
    def to_dynamodb(self) -> Dict:
        """Convert to DynamoDB item format."""
        return {
            "user_id": self.user_id,
            "timestamp": self.timestamp,
            "transaction_id": self.transaction_id,
            "portfolio_id": self.portfolio_id,
            "action": self.action,
            "ticker": self.ticker,
            "quantity": self.quantity,
            "price": Decimal(str(self.price)),
            "commission": Decimal(str(self.commission)),
            "total_cost": Decimal(str(self.total_cost)),
            "execution_status": self.execution_status,
            "order_type": self.order_type,
            "initiated_by": self.initiated_by
        }
    
    @classmethod
    def from_dynamodb(cls, item: Dict) -> 'Transaction':
        """Create Transaction from DynamoDB item."""
        return cls(
            user_id=item["user_id"],
            timestamp=item["timestamp"],
            transaction_id=item["transaction_id"],
            portfolio_id=item["portfolio_id"],
            action=item["action"],
            ticker=item["ticker"],
            quantity=int(item["quantity"]),
            price=float(item["price"]),
            commission=float(item.get("commission", 0.0)),
            total_cost=float(item["total_cost"]),
            execution_status=item["execution_status"],
            order_type=item["order_type"],
            initiated_by=item["initiated_by"]
        )


@dataclass
class AgentState:
    """Represents the state of an agent session."""
    
    session_id: str
    user_id: str
    agent_type: str
    state: Dict
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    ttl: int = 0
    
    def __post_init__(self):
        """Validate agent state data."""
        if not self.session_id:
            raise ValueError("Session ID cannot be empty")
        if not self.user_id:
            raise ValueError("User ID cannot be empty")
        if not self.agent_type:
            raise ValueError("Agent type cannot be empty")
        
        # Set TTL to 24 hours from now if not provided
        if self.ttl == 0:
            self.ttl = int(datetime.utcnow().timestamp()) + 86400
    
    def to_dynamodb(self) -> Dict:
        """Convert to DynamoDB item format."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "agent_type": self.agent_type,
            "state": self.state,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "ttl": self.ttl
        }
    
    @classmethod
    def from_dynamodb(cls, item: Dict) -> 'AgentState':
        """Create AgentState from DynamoDB item."""
        return cls(
            session_id=item["session_id"],
            user_id=item["user_id"],
            agent_type=item["agent_type"],
            state=item["state"],
            created_at=item["created_at"],
            last_updated=item["last_updated"],
            ttl=int(item["ttl"])
        )
