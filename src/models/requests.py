"""Request and response data models for agent interactions."""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime


@dataclass
class SupervisorRequest:
    """Request to the Supervisor Agent."""
    
    user_id: str
    session_id: str
    request_type: str  # "analyze", "rebalance", "tax_optimize"
    parameters: Dict
    context: Dict = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate supervisor request."""
        if not self.user_id:
            raise ValueError("User ID cannot be empty")
        if not self.session_id:
            raise ValueError("Session ID cannot be empty")
        if self.request_type not in ["analyze", "rebalance", "tax_optimize"]:
            raise ValueError(f"Invalid request type: {self.request_type}")


@dataclass
class AnalysisRequest:
    """Request for portfolio analysis."""
    
    user_id: str
    portfolio_id: str
    analysis_type: str  # "performance", "risk", "drift"
    time_period: str  # "1D", "1W", "1M", "1Y", "YTD"
    
    def __post_init__(self):
        """Validate analysis request."""
        if not self.user_id or not self.portfolio_id:
            raise ValueError("User ID and Portfolio ID are required")
        if self.analysis_type not in ["performance", "risk", "drift"]:
            raise ValueError(f"Invalid analysis type: {self.analysis_type}")


@dataclass
class TaxOptimizationRequest:
    """Request for tax optimization."""
    
    user_id: str
    portfolio_id: str
    current_holdings: List
    target_allocation: Dict[str, float]
    tax_year: int
    
    def __post_init__(self):
        """Validate tax optimization request."""
        if not self.user_id or not self.portfolio_id:
            raise ValueError("User ID and Portfolio ID are required")
        if self.tax_year < 2000 or self.tax_year > 2100:
            raise ValueError(f"Invalid tax year: {self.tax_year}")


@dataclass
class RebalancingRequest:
    """Request for portfolio rebalancing."""
    
    user_id: str
    portfolio_id: str
    current_holdings: List
    target_allocation: Dict[str, float]
    constraints: 'RebalancingConstraints'
    
    def __post_init__(self):
        """Validate rebalancing request."""
        if not self.user_id or not self.portfolio_id:
            raise ValueError("User ID and Portfolio ID are required")


@dataclass
class RebalancingConstraints:
    """Constraints for portfolio rebalancing."""
    
    max_transaction_cost: float
    min_trade_size: float
    risk_tolerance: str  # "conservative", "moderate", "aggressive"
    excluded_securities: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate rebalancing constraints."""
        if self.max_transaction_cost < 0:
            raise ValueError("Max transaction cost must be non-negative")
        if self.min_trade_size < 0:
            raise ValueError("Min trade size must be non-negative")
        if self.risk_tolerance not in ["conservative", "moderate", "aggressive"]:
            raise ValueError(f"Invalid risk tolerance: {self.risk_tolerance}")


@dataclass
class Subtask:
    """Represents a subtask in the supervisor workflow."""
    
    subtask_id: str
    subtask_type: str  # "analysis", "tax", "rebalancing"
    agent_name: str  # "portfolio_analyzer", "tax_optimizer", "rebalancing_agent"
    parameters: Dict
    status: str = "pending"  # "pending", "in_progress", "completed", "failed"
    retry_count: int = 0
    
    def __post_init__(self):
        """Validate subtask."""
        if not self.subtask_id:
            raise ValueError("Subtask ID cannot be empty")
        if self.subtask_type not in ["analysis", "tax", "rebalancing"]:
            raise ValueError(f"Invalid subtask type: {self.subtask_type}")
        if self.agent_name not in ["portfolio_analyzer", "tax_optimizer", "rebalancing_agent"]:
            raise ValueError(f"Invalid agent name: {self.agent_name}")
        if self.status not in ["pending", "in_progress", "completed", "failed"]:
            raise ValueError(f"Invalid status: {self.status}")
        if self.retry_count < 0:
            raise ValueError(f"Retry count must be non-negative, got {self.retry_count}")


@dataclass
class CompletedTask:
    """Represents a completed subtask with results."""
    
    subtask_id: str
    subtask_type: str
    agent_name: str
    result: Dict
    completed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def __post_init__(self):
        """Validate completed task."""
        if not self.subtask_id:
            raise ValueError("Subtask ID cannot be empty")
        if not self.result:
            raise ValueError("Result cannot be empty")
