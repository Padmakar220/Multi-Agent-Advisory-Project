"""Rebalancing Agent Lambda handler."""

import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal
import uuid

import boto3
from botocore.exceptions import ClientError

from src.models.portfolio import Portfolio, Holding
from src.models.requests import RebalancingRequest, RebalancingConstraints
from src.models.responses import (
    RebalancingPlan,
    TradeOrder,
    TransactionCosts,
    RiskImpact,
)
from src.mcp_tools.get_portfolio_tool import GetPortfolioTool
from src.mcp_tools.query_market_data_tool import QueryMarketDataTool
from src.error_handling import ErrorClassifier, ErrorCategory
from src.error_handling.circuit_breaker import CircuitBreaker
from src.utils.rag_enricher import RAGEnricher

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Environment variables
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")
DYNAMODB_TABLE_PORTFOLIOS = os.environ.get("DYNAMODB_TABLE_PORTFOLIOS", "Portfolios")
OPENSEARCH_ENDPOINT = os.environ.get("OPENSEARCH_ENDPOINT", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# Initialize AWS clients
bedrock_client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)

# Initialize MCP tools
portfolio_tool = GetPortfolioTool(table_name=DYNAMODB_TABLE_PORTFOLIOS, region_name=AWS_REGION)
market_data_tool = QueryMarketDataTool(
    opensearch_endpoint=OPENSEARCH_ENDPOINT,
    region_name=AWS_REGION
)

# Circuit breaker for Bedrock
bedrock_circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=60)


class RebalancingAgent:
    """Rebalancing Agent for calculating portfolio rebalancing trades."""
    
    def __init__(self):
        """Initialize the Rebalancing Agent."""
        self.portfolio_tool = portfolio_tool
        self.market_data_tool = market_data_tool
        self.bedrock_client = bedrock_client
        self.rag_enricher = RAGEnricher()
    
    def rebalance(
        self,
        user_id: str,
        portfolio_id: str,
        target_allocation: Dict[str, float],
        constraints: RebalancingConstraints
    ) -> RebalancingPlan:
        """
        Calculate rebalancing trades to achieve target allocation.
        
        Args:
            user_id: User identifier
            portfolio_id: Portfolio identifier
            target_allocation: Target allocation percentages by asset class
            constraints: Rebalancing constraints (costs, risk tolerance, etc.)
            
        Returns:
            RebalancingPlan with trade orders and projected allocation
            
        Raises:
            ValueError: If portfolio not found or invalid input
            ClientError: If AWS service calls fail
        """
        logger.info(f"Starting rebalancing for user={user_id}, portfolio={portfolio_id}")
        
        try:
            # Step 1: Retrieve portfolio data
            portfolio = self._retrieve_portfolio(user_id, portfolio_id)
            logger.info(f"Retrieved portfolio with {len(portfolio.holdings)} holdings, value=${portfolio.total_value:.2f}")
            
            # Step 2: Calculate allocation deltas
            allocation_deltas = self._calculate_allocation_deltas(portfolio, target_allocation)
            logger.info(f"Calculated allocation deltas for {len(allocation_deltas)} asset classes")
            
            # Step 3: Generate trade orders
            trade_orders = self._generate_trade_orders(portfolio, allocation_deltas, constraints)
            logger.info(f"Generated {len(trade_orders)} trade orders")
            
            # Step 4: Calculate transaction costs
            transaction_costs = self._calculate_transaction_costs(trade_orders)
            logger.info(f"Calculated transaction costs: ${transaction_costs.total_cost:.2f}")
            
            # Step 5: Check risk tolerance constraints
            self._check_risk_tolerance_constraints(trade_orders, constraints, portfolio)
            logger.info(f"Validated risk tolerance constraints")
            
            # Step 6: Generate Bedrock optimization recommendations
            optimized_trades = self._generate_bedrock_recommendations(
                portfolio,
                trade_orders,
                transaction_costs,
                constraints
            )
            logger.info(f"Generated {len(optimized_trades)} optimized trades from Bedrock")
            
            # Step 7: Calculate projected allocation
            projected_allocation = self._calculate_projected_allocation(portfolio, optimized_trades, target_allocation)
            logger.info(f"Calculated projected allocation")
            
            # Step 8: Calculate risk impact
            risk_impact = self._calculate_risk_impact(portfolio, optimized_trades)
            logger.info(f"Calculated risk impact: {risk_impact.risk_assessment}")
            
            # Step 9: Assemble and return rebalancing plan
            plan = RebalancingPlan(
                portfolio_id=portfolio_id,
                timestamp=datetime.utcnow().isoformat(),
                trade_orders=optimized_trades,
                expected_costs=transaction_costs,
                projected_allocation=projected_allocation,
                risk_impact=risk_impact
            )
            
            logger.info(f"Rebalancing plan complete for portfolio {portfolio_id}")
            return plan
            
        except ValueError as e:
            logger.error(f"Validation error during rebalancing: {str(e)}")
            raise
        except ClientError as e:
            logger.error(f"AWS service error during rebalancing: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during rebalancing: {str(e)}")
            raise
    
    def _retrieve_portfolio(self, user_id: str, portfolio_id: str) -> Portfolio:
        """Retrieve portfolio from DynamoDB."""
        try:
            portfolio = self.portfolio_tool.execute(user_id, portfolio_id)
            return portfolio
        except ValueError as e:
            logger.error(f"Portfolio not found: {str(e)}")
            raise
        except ClientError as e:
            category = ErrorClassifier.categorize(e)
            if category == ErrorCategory.TRANSIENT:
                logger.warning(f"Transient error retrieving portfolio, will retry: {str(e)}")
            raise
    
    def _calculate_allocation_deltas(
        self,
        portfolio: Portfolio,
        target_allocation: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Calculate difference between current and target allocation for each asset class.
        
        Returns dict mapping asset class to delta (positive = need to buy, negative = need to sell)
        """
        # Map tickers to asset classes
        asset_class_mapping = {
            "VTI": "stocks",
            "VTSAX": "stocks",
            "FSKAX": "stocks",
            "VXUS": "stocks",
            "VTIAX": "stocks",
            "FTIHX": "stocks",
            "BND": "bonds",
            "VBTLX": "bonds",
            "VGIT": "bonds",
            "FXNAX": "bonds",
            "VGSLX": "bonds",
            "VMFXX": "cash",
        }
        
        # Calculate current allocation
        total_value = portfolio.total_value
        current_allocation = {}
        
        if total_value > 0:
            for holding in portfolio.holdings:
                asset_class = asset_class_mapping.get(holding.ticker, "other")
                if asset_class not in current_allocation:
                    current_allocation[asset_class] = 0.0
                current_allocation[asset_class] += holding.market_value / total_value
        
        # Ensure all asset classes are represented
        for asset_class in target_allocation:
            if asset_class not in current_allocation:
                current_allocation[asset_class] = 0.0
        
        # Calculate deltas (in dollar amounts)
        allocation_deltas = {}
        for asset_class in target_allocation:
            current_pct = current_allocation.get(asset_class, 0.0)
            target_pct = target_allocation.get(asset_class, 0.0)
            delta_pct = target_pct - current_pct
            delta_dollars = delta_pct * total_value
            allocation_deltas[asset_class] = delta_dollars
        
        return allocation_deltas
    
    def _generate_trade_orders(
        self,
        portfolio: Portfolio,
        allocation_deltas: Dict[str, float],
        constraints: RebalancingConstraints
    ) -> List[TradeOrder]:
        """Generate specific buy/sell orders to achieve target allocation."""
        trade_orders = []
        
        # Map asset classes to representative tickers
        asset_class_tickers = {
            "stocks": "VTI",
            "bonds": "BND",
            "cash": "VMFXX",
        }
        
        # Get current market prices (simplified - would use market data tool in production)
        current_prices = self._get_current_prices(portfolio)
        
        for asset_class, delta_dollars in allocation_deltas.items():
            if abs(delta_dollars) < constraints.min_trade_size:
                # Skip trades below minimum size
                continue
            
            ticker = asset_class_tickers.get(asset_class, "VTI")
            current_price = current_prices.get(ticker, 100.0)
            
            if delta_dollars > 0:
                # Buy order
                quantity = int(delta_dollars / current_price)
                if quantity > 0:
                    order = TradeOrder(
                        order_id=str(uuid.uuid4()),
                        action="buy",
                        ticker=ticker,
                        quantity=quantity,
                        order_type="market",
                        estimated_price=current_price,
                        estimated_cost=quantity * current_price
                    )
                    trade_orders.append(order)
            elif delta_dollars < 0:
                # Sell order
                quantity = int(abs(delta_dollars) / current_price)
                if quantity > 0:
                    order = TradeOrder(
                        order_id=str(uuid.uuid4()),
                        action="sell",
                        ticker=ticker,
                        quantity=quantity,
                        order_type="market",
                        estimated_price=current_price,
                        estimated_cost=quantity * current_price
                    )
                    trade_orders.append(order)
        
        return trade_orders
    
    def _get_current_prices(self, portfolio: Portfolio) -> Dict[str, float]:
        """Get current market prices for holdings."""
        prices = {}
        for holding in portfolio.holdings:
            prices[holding.ticker] = holding.current_price
        return prices
    
    def _calculate_transaction_costs(self, trade_orders: List[TradeOrder]) -> TransactionCosts:
        """Calculate total transaction costs for all trades."""
        total_commission = 0.0
        total_slippage = 0.0
        
        for order in trade_orders:
            # Commission: $0 for most brokers (simplified)
            commission = 0.0
            
            # Slippage: estimate 0.1% of trade value
            slippage = order.estimated_cost * 0.001
            
            total_commission += commission
            total_slippage += slippage
        
        total_cost = total_commission + total_slippage
        
        return TransactionCosts(
            total_commission=total_commission,
            estimated_slippage=total_slippage,
            total_cost=total_cost
        )
    
    def _check_risk_tolerance_constraints(
        self,
        trade_orders: List[TradeOrder],
        constraints: RebalancingConstraints,
        portfolio: Portfolio
    ) -> None:
        """Validate trades respect risk tolerance constraints."""
        # Check transaction cost constraint
        total_cost = sum(order.estimated_cost for order in trade_orders)
        if total_cost > constraints.max_transaction_cost:
            logger.warning(
                f"Total transaction cost ${total_cost:.2f} exceeds max ${constraints.max_transaction_cost:.2f}"
            )
        
        # Check excluded securities
        for order in trade_orders:
            if order.ticker in constraints.excluded_securities:
                raise ValueError(f"Trade order for excluded security {order.ticker}")
        
        # Check risk tolerance constraints
        if constraints.risk_tolerance == "conservative":
            # Conservative portfolios should avoid high-volatility trades
            high_volatility_tickers = ["VXUS", "VTIAX"]  # International stocks
            for order in trade_orders:
                if order.ticker in high_volatility_tickers and order.action == "buy":
                    logger.warning(
                        f"Conservative portfolio buying high-volatility security {order.ticker}"
                    )
    
    def _generate_bedrock_recommendations(
        self,
        portfolio: Portfolio,
        trade_orders: List[TradeOrder],
        transaction_costs: TransactionCosts,
        constraints: RebalancingConstraints,
        session_id: str = "",
    ) -> List[TradeOrder]:
        """Generate optimized trades using Bedrock with RAG enrichment."""
        try:
            # RAG enrichment before prompt construction
            query = f"Rebalancing plan for portfolio {portfolio.portfolio_name}"
            rag_context = self.rag_enricher.enrich(query, session_id or portfolio.portfolio_id)

            prompt = self._build_rebalancing_prompt(
                portfolio, trade_orders, transaction_costs, constraints
            )
            if rag_context.has_context:
                prompt = prompt + "\n\n" + rag_context.format_context_block()

            response = self._invoke_bedrock_with_retry(prompt, max_retries=2)
            return self._parse_bedrock_trades(response, trade_orders)

        except Exception as e:
            logger.error(f"Error generating Bedrock recommendations: {str(e)}")
            return trade_orders
    
    def _build_rebalancing_prompt(
        self,
        portfolio: Portfolio,
        trade_orders: List[TradeOrder],
        transaction_costs: TransactionCosts,
        constraints: RebalancingConstraints
    ) -> str:
        """Build prompt for Bedrock rebalancing optimization."""
        prompt = f"""Analyze the following portfolio rebalancing plan and provide optimization recommendations:

Portfolio: {portfolio.portfolio_name}
Total Value: ${portfolio.total_value:.2f}
Risk Tolerance: {portfolio.risk_tolerance}

Current Holdings:
"""
        for holding in portfolio.holdings:
            prompt += f"- {holding.ticker}: {holding.quantity} shares @ ${holding.current_price:.2f} (value: ${holding.market_value:.2f})\n"
        
        prompt += f"""
Proposed Trades ({len(trade_orders)} total):
"""
        for trade in trade_orders:
            prompt += f"- {trade.action.upper()} {trade.quantity} shares of {trade.ticker} @ ${trade.estimated_price:.2f} (cost: ${trade.estimated_cost:.2f})\n"
        
        prompt += f"""
Transaction Costs:
- Commission: ${transaction_costs.total_commission:.2f}
- Estimated Slippage: ${transaction_costs.estimated_slippage:.2f}
- Total Cost: ${transaction_costs.total_cost:.2f}

Constraints:
- Max Transaction Cost: ${constraints.max_transaction_cost:.2f}
- Min Trade Size: ${constraints.min_trade_size:.2f}
- Risk Tolerance: {constraints.risk_tolerance}
- Excluded Securities: {', '.join(constraints.excluded_securities) if constraints.excluded_securities else 'None'}

Based on this analysis, provide recommendations for optimizing the rebalancing plan.
Consider:
1. Whether all proposed trades are necessary
2. Whether the order of trades matters
3. Whether any trades should be deferred
4. Whether the total cost is acceptable

Format your response as a JSON object with the following structure:
{{
    "recommended_trades": [
        {{
            "action": "buy" or "sell",
            "ticker": "TICKER",
            "quantity": number,
            "order_type": "market" or "limit",
            "estimated_price": number,
            "estimated_cost": number
        }}
    ],
    "total_cost": number,
    "notes": "additional recommendations"
}}"""
        
        return prompt
    
    def _invoke_bedrock_with_retry(self, prompt: str, max_retries: int = 2) -> str:
        """Invoke Bedrock Claude model with retry logic."""
        retry_count = 0
        last_error = None
        
        while retry_count <= max_retries:
            try:
                response = bedrock_circuit_breaker.call(
                    self._invoke_bedrock,
                    prompt
                )
                return response
            except Exception as e:
                last_error = e
                retry_count += 1
                
                if retry_count <= max_retries:
                    logger.warning(f"Bedrock invocation failed (attempt {retry_count}), retrying: {str(e)}")
                    import time
                    time.sleep(2 ** retry_count)
                else:
                    logger.error(f"Bedrock invocation failed after {max_retries} retries: {str(e)}")
        
        raise last_error
    
    def _invoke_bedrock(self, prompt: str) -> str:
        """Invoke Bedrock Claude model."""
        try:
            response = self.bedrock_client.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-06-01",
                    "max_tokens": 1024,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                })
            )
            
            # Parse response
            response_body = json.loads(response["body"].read())
            
            # Extract text from response
            if "content" in response_body and len(response_body["content"]) > 0:
                return response_body["content"][0]["text"]
            else:
                raise ValueError("Invalid Bedrock response format")
                
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "ThrottlingException":
                raise Exception(f"Bedrock throttled: {str(e)}")
            elif error_code == "ValidationException":
                raise ValueError(f"Invalid Bedrock request: {str(e)}")
            else:
                raise Exception(f"Bedrock error: {str(e)}")
    
    def _parse_bedrock_trades(self, response: str, fallback_trades: List[TradeOrder]) -> List[TradeOrder]:
        """Parse trades from Bedrock response."""
        try:
            # Extract JSON from response
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            
            if json_start == -1 or json_end == 0:
                logger.warning("No JSON found in Bedrock response, using fallback trades")
                return fallback_trades
            
            json_str = response[json_start:json_end]
            data = json.loads(json_str)
            
            # Parse trades from response
            trades = []
            for trade_data in data.get("recommended_trades", []):
                trade = TradeOrder(
                    order_id=str(uuid.uuid4()),
                    action=trade_data.get("action", "buy"),
                    ticker=trade_data.get("ticker", ""),
                    quantity=int(trade_data.get("quantity", 0)),
                    order_type=trade_data.get("order_type", "market"),
                    estimated_price=float(trade_data.get("estimated_price", 0.0)),
                    estimated_cost=float(trade_data.get("estimated_cost", 0.0))
                )
                trades.append(trade)
            
            return trades if trades else fallback_trades
            
        except Exception as e:
            logger.warning(f"Error parsing Bedrock trades: {str(e)}, using fallback trades")
            return fallback_trades
    
    def _calculate_projected_allocation(
        self,
        portfolio: Portfolio,
        trade_orders: List[TradeOrder],
        target_allocation: Dict[str, float]
    ) -> Dict[str, float]:
        """Calculate projected allocation after executing trades."""
        # Map tickers to asset classes
        asset_class_mapping = {
            "VTI": "stocks",
            "VTSAX": "stocks",
            "FSKAX": "stocks",
            "VXUS": "stocks",
            "VTIAX": "stocks",
            "FTIHX": "stocks",
            "BND": "bonds",
            "VBTLX": "bonds",
            "VGIT": "bonds",
            "FXNAX": "bonds",
            "VGSLX": "bonds",
            "VMFXX": "cash",
        }
        
        # Start with current holdings
        projected_values = {}
        for holding in portfolio.holdings:
            asset_class = asset_class_mapping.get(holding.ticker, "other")
            if asset_class not in projected_values:
                projected_values[asset_class] = 0.0
            projected_values[asset_class] += holding.market_value
        
        # Apply trades
        for trade in trade_orders:
            asset_class = asset_class_mapping.get(trade.ticker, "other")
            if asset_class not in projected_values:
                projected_values[asset_class] = 0.0
            
            if trade.action == "buy":
                projected_values[asset_class] += trade.estimated_cost
            elif trade.action == "sell":
                projected_values[asset_class] -= trade.estimated_cost
        
        # Calculate projected allocation percentages
        total_value = sum(projected_values.values())
        projected_allocation = {}
        
        if total_value > 0:
            for asset_class in target_allocation:
                projected_allocation[asset_class] = projected_values.get(asset_class, 0.0) / total_value
        else:
            projected_allocation = dict(target_allocation)
        
        return projected_allocation
    
    def _calculate_risk_impact(
        self,
        portfolio: Portfolio,
        trade_orders: List[TradeOrder]
    ) -> RiskImpact:
        """Calculate risk impact of rebalancing."""
        # Simplified risk calculation
        current_risk_score = self._calculate_risk_score(portfolio)
        
        # Estimate projected risk (simplified)
        projected_risk_score = current_risk_score * 0.95  # Assume rebalancing reduces risk
        
        risk_change = projected_risk_score - current_risk_score
        
        if risk_change < -0.05:
            risk_assessment = "reduced"
        elif risk_change > 0.05:
            risk_assessment = "increased"
        else:
            risk_assessment = "unchanged"
        
        return RiskImpact(
            current_risk_score=current_risk_score,
            projected_risk_score=projected_risk_score,
            risk_change=risk_change,
            risk_assessment=risk_assessment
        )
    
    def _calculate_risk_score(self, portfolio: Portfolio) -> float:
        """Calculate portfolio risk score (0-1, where 1 is highest risk)."""
        if not portfolio.holdings:
            return 0.0
        
        # Simplified risk calculation based on concentration
        total_value = portfolio.total_value
        if total_value == 0:
            return 0.0
        
        # Calculate Herfindahl index (concentration measure)
        herfindahl = sum((h.market_value / total_value) ** 2 for h in portfolio.holdings)
        
        # Normalize to 0-1 range
        risk_score = herfindahl
        
        return risk_score


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for Rebalancing Agent.
    
    Expected event structure:
    {
        "user_id": "user_123",
        "portfolio_id": "portfolio_456",
        "target_allocation": {"stocks": 0.6, "bonds": 0.3, "cash": 0.1},
        "constraints": {
            "max_transaction_cost": 100.0,
            "min_trade_size": 50.0,
            "risk_tolerance": "moderate",
            "excluded_securities": []
        }
    }
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Extract parameters
        user_id = event.get("user_id")
        portfolio_id = event.get("portfolio_id")
        target_allocation = event.get("target_allocation", {})
        constraints_data = event.get("constraints", {})
        
        # Validate input
        if not user_id or not portfolio_id:
            raise ValueError("user_id and portfolio_id are required")
        if not target_allocation:
            raise ValueError("target_allocation is required")
        
        # Create constraints object
        constraints = RebalancingConstraints(
            max_transaction_cost=constraints_data.get("max_transaction_cost", 1000.0),
            min_trade_size=constraints_data.get("min_trade_size", 50.0),
            risk_tolerance=constraints_data.get("risk_tolerance", "moderate"),
            excluded_securities=constraints_data.get("excluded_securities", [])
        )
        
        # Perform rebalancing
        agent = RebalancingAgent()
        plan = agent.rebalance(user_id, portfolio_id, target_allocation, constraints)
        
        # Return success response
        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "success",
                "portfolio_id": plan.portfolio_id,
                "timestamp": plan.timestamp,
                "trade_orders": [
                    {
                        "order_id": order.order_id,
                        "action": order.action,
                        "ticker": order.ticker,
                        "quantity": order.quantity,
                        "order_type": order.order_type,
                        "estimated_price": order.estimated_price,
                        "estimated_cost": order.estimated_cost
                    }
                    for order in plan.trade_orders
                ],
                "expected_costs": {
                    "total_commission": plan.expected_costs.total_commission,
                    "estimated_slippage": plan.expected_costs.estimated_slippage,
                    "total_cost": plan.expected_costs.total_cost
                },
                "projected_allocation": plan.projected_allocation,
                "risk_impact": {
                    "current_risk_score": plan.risk_impact.current_risk_score,
                    "projected_risk_score": plan.risk_impact.projected_risk_score,
                    "risk_change": plan.risk_impact.risk_change,
                    "risk_assessment": plan.risk_impact.risk_assessment
                }
            })
        }
        
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        return {
            "statusCode": 400,
            "body": json.dumps({
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "error_message": str(e)
            })
        }
    except ClientError as e:
        logger.error(f"AWS service error: {str(e)}")
        error_code = e.response.get("Error", {}).get("Code", "UNKNOWN")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "error",
                "error_code": "AGENT_ERROR",
                "error_message": f"AWS service error: {error_code}"
            })
        }
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "error",
                "error_code": "SYSTEM_ERROR",
                "error_message": "An unexpected error occurred"
            })
        }
