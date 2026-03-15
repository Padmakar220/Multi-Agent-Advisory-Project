"""Data models and schemas for the Multi-Agent Advisory AI System."""

from src.models.portfolio import (
    Holding,
    Portfolio,
    Transaction,
    AgentState
)

from src.models.requests import (
    SupervisorRequest,
    AnalysisRequest,
    TaxOptimizationRequest,
    RebalancingRequest,
    RebalancingConstraints,
    Subtask,
    CompletedTask
)

from src.models.responses import (
    PerformanceMetrics,
    RiskMetrics,
    AllocationDrift,
    MarketInsight,
    AnalysisReport,
    TaxLossOpportunity,
    TaxOptimizedTrade,
    WashSaleWarning,
    TaxOptimizationPlan,
    TradeOrder,
    TransactionCosts,
    RiskImpact,
    RebalancingPlan,
    SupervisorResponse,
    ErrorResponse,
    TradeConfirmation,
    CostBasisInfo,
    MarketData,
    ApprovalPayload,
    ErrorDetails
)

__all__ = [
    # Portfolio models
    "Holding",
    "Portfolio",
    "Transaction",
    "AgentState",
    # Request models
    "SupervisorRequest",
    "AnalysisRequest",
    "TaxOptimizationRequest",
    "RebalancingRequest",
    "RebalancingConstraints",
    "Subtask",
    "CompletedTask",
    # Response models
    "PerformanceMetrics",
    "RiskMetrics",
    "AllocationDrift",
    "MarketInsight",
    "AnalysisReport",
    "TaxLossOpportunity",
    "TaxOptimizedTrade",
    "WashSaleWarning",
    "TaxOptimizationPlan",
    "TradeOrder",
    "TransactionCosts",
    "RiskImpact",
    "RebalancingPlan",
    "SupervisorResponse",
    "ErrorResponse",
    "TradeConfirmation",
    "CostBasisInfo",
    "MarketData",
    "ApprovalPayload",
    "ErrorDetails"
]
