"""Response data models for agent outputs."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional
from decimal import Decimal


@dataclass
class PerformanceMetrics:
    """Performance metrics for portfolio analysis."""
    
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    
    def __post_init__(self):
        """Validate performance metrics."""
        if self.max_drawdown > 0:
            raise ValueError(f"Max drawdown must be non-positive, got {self.max_drawdown}")


@dataclass
class RiskMetrics:
    """Risk metrics for portfolio analysis."""
    
    portfolio_volatility: float
    beta: float
    var_95: float  # Value at Risk at 95% confidence
    concentration_risk: Dict[str, float]
    
    def __post_init__(self):
        """Validate risk metrics."""
        if self.portfolio_volatility < 0:
            raise ValueError(f"Portfolio volatility must be non-negative, got {self.portfolio_volatility}")
        if self.var_95 > 0:
            raise ValueError(f"VaR should be non-positive, got {self.var_95}")


@dataclass
class AllocationDrift:
    """Allocation drift analysis."""
    
    current_allocation: Dict[str, float]
    target_allocation: Dict[str, float]
    drift_percentage: Dict[str, float]
    rebalancing_needed: bool
    
    def __post_init__(self):
        """Validate allocation drift."""
        # Validate allocations sum to approximately 1.0
        current_sum = sum(self.current_allocation.values())
        target_sum = sum(self.target_allocation.values())
        
        if abs(current_sum - 1.0) > 0.01:
            raise ValueError(f"Current allocation must sum to 1.0, got {current_sum}")
        if abs(target_sum - 1.0) > 0.01:
            raise ValueError(f"Target allocation must sum to 1.0, got {target_sum}")


@dataclass
class MarketInsight:
    """Market insight from OpenSearch."""
    
    title: str
    content: str
    ticker: Optional[str]
    sector: Optional[str]
    timestamp: str
    source: str
    relevance_score: float
    
    def __post_init__(self):
        """Validate market insight."""
        if not self.title or not self.content:
            raise ValueError("Title and content are required")
        if self.relevance_score < 0 or self.relevance_score > 1:
            raise ValueError(f"Relevance score must be between 0 and 1, got {self.relevance_score}")


@dataclass
class AnalysisReport:
    """Portfolio analysis report."""
    
    portfolio_id: str
    timestamp: str
    performance_metrics: PerformanceMetrics
    risk_metrics: RiskMetrics
    allocation_drift: AllocationDrift
    market_context: List[MarketInsight]
    recommendations: List[str]
    
    def __post_init__(self):
        """Validate analysis report."""
        if not self.portfolio_id:
            raise ValueError("Portfolio ID cannot be empty")
    
    def to_dynamodb(self) -> Dict:
        """Convert to DynamoDB item format."""
        return {
            "portfolio_id": self.portfolio_id,
            "timestamp": self.timestamp,
            "performance_metrics": {
                "total_return": Decimal(str(self.performance_metrics.total_return)),
                "annualized_return": Decimal(str(self.performance_metrics.annualized_return)),
                "sharpe_ratio": Decimal(str(self.performance_metrics.sharpe_ratio)),
                "max_drawdown": Decimal(str(self.performance_metrics.max_drawdown))
            },
            "risk_metrics": {
                "portfolio_volatility": Decimal(str(self.risk_metrics.portfolio_volatility)),
                "beta": Decimal(str(self.risk_metrics.beta)),
                "var_95": Decimal(str(self.risk_metrics.var_95)),
                "concentration_risk": {k: Decimal(str(v)) for k, v in self.risk_metrics.concentration_risk.items()}
            },
            "allocation_drift": {
                "current_allocation": {k: Decimal(str(v)) for k, v in self.allocation_drift.current_allocation.items()},
                "target_allocation": {k: Decimal(str(v)) for k, v in self.allocation_drift.target_allocation.items()},
                "drift_percentage": {k: Decimal(str(v)) for k, v in self.allocation_drift.drift_percentage.items()},
                "rebalancing_needed": self.allocation_drift.rebalancing_needed
            },
            "market_context": [
                {
                    "title": insight.title,
                    "content": insight.content,
                    "ticker": insight.ticker,
                    "sector": insight.sector,
                    "timestamp": insight.timestamp,
                    "source": insight.source,
                    "relevance_score": Decimal(str(insight.relevance_score))
                }
                for insight in self.market_context
            ],
            "recommendations": self.recommendations
        }


@dataclass
class TaxLossOpportunity:
    """Tax loss harvesting opportunity."""
    
    ticker: str
    quantity: int
    cost_basis: float
    current_value: float
    unrealized_loss: float
    potential_tax_savings: float
    replacement_security: Optional[str] = None
    
    def __post_init__(self):
        """Validate tax loss opportunity."""
        if not self.ticker:
            raise ValueError("Ticker cannot be empty")
        if self.quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {self.quantity}")
        if self.unrealized_loss >= 0:
            raise ValueError(f"Unrealized loss must be negative, got {self.unrealized_loss}")
        if self.potential_tax_savings < 0:
            raise ValueError(f"Potential tax savings must be non-negative, got {self.potential_tax_savings}")


@dataclass
class TaxOptimizedTrade:
    """Tax-optimized trade recommendation."""
    
    action: str  # "sell", "buy"
    ticker: str
    quantity: int
    reason: str
    tax_impact: float
    
    def __post_init__(self):
        """Validate tax-optimized trade."""
        if self.action not in ["sell", "buy"]:
            raise ValueError(f"Action must be 'sell' or 'buy', got {self.action}")
        if not self.ticker:
            raise ValueError("Ticker cannot be empty")
        if self.quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {self.quantity}")


@dataclass
class WashSaleWarning:
    """Warning about potential wash sale violation."""
    
    ticker: str
    sale_date: str
    purchase_date: str
    days_between: int
    warning_message: str
    
    def __post_init__(self):
        """Validate wash sale warning."""
        if self.days_between < 0:
            raise ValueError(f"Days between must be non-negative, got {self.days_between}")


@dataclass
class TaxOptimizationPlan:
    """Tax optimization plan."""
    
    portfolio_id: str
    timestamp: str
    tax_loss_opportunities: List[TaxLossOpportunity]
    total_potential_savings: float
    recommended_trades: List[TaxOptimizedTrade]
    wash_sale_warnings: List[WashSaleWarning] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate tax optimization plan."""
        if not self.portfolio_id:
            raise ValueError("Portfolio ID cannot be empty")
        if self.total_potential_savings < 0:
            raise ValueError(f"Total potential savings must be non-negative, got {self.total_potential_savings}")
    
    def to_dynamodb(self) -> Dict:
        """Convert to DynamoDB item format."""
        return {
            "portfolio_id": self.portfolio_id,
            "timestamp": self.timestamp,
            "tax_loss_opportunities": [
                {
                    "ticker": opp.ticker,
                    "quantity": opp.quantity,
                    "cost_basis": Decimal(str(opp.cost_basis)),
                    "current_value": Decimal(str(opp.current_value)),
                    "unrealized_loss": Decimal(str(opp.unrealized_loss)),
                    "potential_tax_savings": Decimal(str(opp.potential_tax_savings)),
                    "replacement_security": opp.replacement_security
                }
                for opp in self.tax_loss_opportunities
            ],
            "total_potential_savings": Decimal(str(self.total_potential_savings)),
            "recommended_trades": [
                {
                    "action": trade.action,
                    "ticker": trade.ticker,
                    "quantity": trade.quantity,
                    "reason": trade.reason,
                    "tax_impact": Decimal(str(trade.tax_impact))
                }
                for trade in self.recommended_trades
            ],
            "wash_sale_warnings": [
                {
                    "ticker": warning.ticker,
                    "sale_date": warning.sale_date,
                    "purchase_date": warning.purchase_date,
                    "days_between": warning.days_between,
                    "warning_message": warning.warning_message
                }
                for warning in self.wash_sale_warnings
            ]
        }


@dataclass
class TradeOrder:
    """Trade order for rebalancing."""
    
    order_id: str
    action: str  # "buy", "sell", "hold"
    ticker: str
    quantity: int
    order_type: str  # "market", "limit"
    estimated_price: float
    estimated_cost: float
    
    def __post_init__(self):
        """Validate trade order."""
        if self.action not in ["buy", "sell", "hold"]:
            raise ValueError(f"Action must be 'buy', 'sell', or 'hold', got {self.action}")
        if not self.ticker:
            raise ValueError("Ticker cannot be empty")
        if self.quantity < 0:
            raise ValueError(f"Quantity must be non-negative, got {self.quantity}")
        if self.order_type not in ["market", "limit"]:
            raise ValueError(f"Order type must be 'market' or 'limit', got {self.order_type}")
        if self.estimated_price < 0:
            raise ValueError(f"Estimated price must be non-negative, got {self.estimated_price}")


@dataclass
class TransactionCosts:
    """Transaction costs for rebalancing."""
    
    total_commission: float
    estimated_slippage: float
    total_cost: float
    
    def __post_init__(self):
        """Validate transaction costs."""
        if self.total_commission < 0:
            raise ValueError(f"Total commission must be non-negative, got {self.total_commission}")
        if self.estimated_slippage < 0:
            raise ValueError(f"Estimated slippage must be non-negative, got {self.estimated_slippage}")
        if self.total_cost < 0:
            raise ValueError(f"Total cost must be non-negative, got {self.total_cost}")


@dataclass
class RiskImpact:
    """Risk impact of rebalancing."""
    
    current_risk_score: float
    projected_risk_score: float
    risk_change: float
    risk_assessment: str  # "reduced", "increased", "unchanged"
    
    def __post_init__(self):
        """Validate risk impact."""
        if self.current_risk_score < 0:
            raise ValueError(f"Current risk score must be non-negative, got {self.current_risk_score}")
        if self.projected_risk_score < 0:
            raise ValueError(f"Projected risk score must be non-negative, got {self.projected_risk_score}")
        if self.risk_assessment not in ["reduced", "increased", "unchanged"]:
            raise ValueError(f"Invalid risk assessment: {self.risk_assessment}")


@dataclass
class RebalancingPlan:
    """Portfolio rebalancing plan."""
    
    portfolio_id: str
    timestamp: str
    trade_orders: List[TradeOrder]
    expected_costs: TransactionCosts
    projected_allocation: Dict[str, float]
    risk_impact: RiskImpact
    
    def __post_init__(self):
        """Validate rebalancing plan."""
        if not self.portfolio_id:
            raise ValueError("Portfolio ID cannot be empty")
        
        # Validate projected allocation sums to approximately 1.0
        allocation_sum = sum(self.projected_allocation.values())
        if abs(allocation_sum - 1.0) > 0.01:
            raise ValueError(f"Projected allocation must sum to 1.0, got {allocation_sum}")
    
    def to_dynamodb(self) -> Dict:
        """Convert to DynamoDB item format."""
        return {
            "portfolio_id": self.portfolio_id,
            "timestamp": self.timestamp,
            "trade_orders": [
                {
                    "order_id": order.order_id,
                    "action": order.action,
                    "ticker": order.ticker,
                    "quantity": order.quantity,
                    "order_type": order.order_type,
                    "estimated_price": Decimal(str(order.estimated_price)),
                    "estimated_cost": Decimal(str(order.estimated_cost))
                }
                for order in self.trade_orders
            ],
            "expected_costs": {
                "total_commission": Decimal(str(self.expected_costs.total_commission)),
                "estimated_slippage": Decimal(str(self.expected_costs.estimated_slippage)),
                "total_cost": Decimal(str(self.expected_costs.total_cost))
            },
            "projected_allocation": {k: Decimal(str(v)) for k, v in self.projected_allocation.items()},
            "risk_impact": {
                "current_risk_score": Decimal(str(self.risk_impact.current_risk_score)),
                "projected_risk_score": Decimal(str(self.risk_impact.projected_risk_score)),
                "risk_change": Decimal(str(self.risk_impact.risk_change)),
                "risk_assessment": self.risk_impact.risk_assessment
            }
        }


@dataclass
class SupervisorResponse:
    """Response from Supervisor Agent."""
    
    session_id: str
    status: str  # "success", "pending_approval", "error"
    results: Dict
    requires_approval: bool
    approval_payload: Optional[Dict] = None
    error_details: Optional[Dict] = None
    
    def __post_init__(self):
        """Validate supervisor response."""
        if not self.session_id:
            raise ValueError("Session ID cannot be empty")
        if self.status not in ["success", "pending_approval", "error"]:
            raise ValueError(f"Invalid status: {self.status}")
        if self.status == "error" and not self.error_details:
            raise ValueError("Error details required when status is 'error'")
        if self.requires_approval and not self.approval_payload:
            raise ValueError("Approval payload required when approval is needed")


@dataclass
class ErrorResponse:
    """Standardized error response."""
    
    error_code: str  # "AGENT_ERROR", "VALIDATION_ERROR", "SYSTEM_ERROR"
    error_message: str
    error_details: Dict
    recovery_suggestions: List[str]
    support_reference: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def __post_init__(self):
        """Validate error response."""
        valid_codes = ["AGENT_ERROR", "VALIDATION_ERROR", "SYSTEM_ERROR", "TRANSIENT_ERROR", "PERMANENT_ERROR", "CRITICAL_ERROR"]
        if self.error_code not in valid_codes:
            raise ValueError(f"Invalid error code: {self.error_code}")
        if not self.error_message:
            raise ValueError("Error message cannot be empty")


@dataclass
class TradeConfirmation:
    """Confirmation of trade execution."""
    
    order_id: str
    transaction_id: str
    ticker: str
    action: str  # "buy", "sell"
    quantity: int
    execution_price: float
    execution_time: str
    status: str  # "completed", "failed", "partial"
    commission: float = 0.0
    error_message: Optional[str] = None
    
    def __post_init__(self):
        """Validate trade confirmation."""
        if not self.order_id or not self.transaction_id:
            raise ValueError("Order ID and Transaction ID are required")
        if self.action not in ["buy", "sell"]:
            raise ValueError(f"Action must be 'buy' or 'sell', got {self.action}")
        if self.quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {self.quantity}")
        if self.execution_price < 0:
            raise ValueError(f"Execution price must be non-negative, got {self.execution_price}")
        if self.status not in ["completed", "failed", "partial"]:
            raise ValueError(f"Invalid status: {self.status}")
        if self.status == "failed" and not self.error_message:
            raise ValueError("Error message required when status is 'failed'")


@dataclass
class CostBasisInfo:
    """Cost basis information for a security."""
    
    ticker: str
    quantity: int
    cost_per_share: float
    purchase_date: str
    total_cost_basis: float = 0.0
    
    def __post_init__(self):
        """Validate cost basis info."""
        if not self.ticker:
            raise ValueError("Ticker cannot be empty")
        if self.quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {self.quantity}")
        if self.cost_per_share < 0:
            raise ValueError(f"Cost per share must be non-negative, got {self.cost_per_share}")
        
        # Calculate total cost basis if not provided
        if self.total_cost_basis == 0.0:
            self.total_cost_basis = self.quantity * self.cost_per_share


@dataclass
class MarketData:
    """Market data result from OpenSearch."""
    
    document_id: str
    document_type: str
    title: str
    content: str
    ticker: Optional[str]
    sector: Optional[str]
    timestamp: str
    source: str
    similarity_score: float
    metadata: Dict = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate market data."""
        if not self.document_id or not self.title:
            raise ValueError("Document ID and title are required")
        if self.similarity_score < 0 or self.similarity_score > 1:
            raise ValueError(f"Similarity score must be between 0 and 1, got {self.similarity_score}")


@dataclass
class ApprovalPayload:
    """Payload for human approval workflow."""
    
    session_id: str
    trade_plan: 'RebalancingPlan'
    tax_implications: Dict[str, float]
    expected_costs: 'TransactionCosts'
    projected_outcomes: Dict[str, float]
    approval_deadline: str
    
    def __post_init__(self):
        """Validate approval payload."""
        if not self.session_id:
            raise ValueError("Session ID cannot be empty")
        if not self.tax_implications:
            raise ValueError("Tax implications are required")
        if not self.projected_outcomes:
            raise ValueError("Projected outcomes are required")


@dataclass
class ErrorDetails:
    """Detailed error information."""
    
    error_type: str
    error_message: str
    stack_trace: Optional[str] = None
    context: Dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def __post_init__(self):
        """Validate error details."""
        if not self.error_type or not self.error_message:
            raise ValueError("Error type and message are required")
