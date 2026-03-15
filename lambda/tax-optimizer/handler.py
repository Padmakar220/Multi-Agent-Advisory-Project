"""Tax Optimizer Agent Lambda handler."""

import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

import boto3
from botocore.exceptions import ClientError

from src.models.portfolio import Portfolio, Holding
from src.models.responses import (
    TaxOptimizationPlan,
    TaxLossOpportunity,
    TaxOptimizedTrade,
    WashSaleWarning,
    CostBasisInfo,
)
from src.mcp_tools.get_portfolio_tool import GetPortfolioTool
from src.mcp_tools.get_cost_basis_tool import GetCostBasisTool
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
cost_basis_tool = GetCostBasisTool(table_name=DYNAMODB_TABLE_PORTFOLIOS, region_name=AWS_REGION)
market_data_tool = QueryMarketDataTool(
    opensearch_endpoint=OPENSEARCH_ENDPOINT,
    region_name=AWS_REGION
)

# Circuit breaker for Bedrock
bedrock_circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=60)


class TaxOptimizer:
    """Tax Optimizer Agent for identifying tax-loss harvesting opportunities."""
    
    def __init__(self, tax_rate: float = 0.24):
        """
        Initialize the Tax Optimizer.
        
        Args:
            tax_rate: Marginal tax rate for tax savings calculation (default 24%)
        """
        self.portfolio_tool = portfolio_tool
        self.cost_basis_tool = cost_basis_tool
        self.market_data_tool = market_data_tool
        self.bedrock_client = bedrock_client
        self.tax_rate = tax_rate
        self.rag_enricher = RAGEnricher()
    
    def optimize(self, user_id: str, portfolio_id: str, tax_year: int = None) -> TaxOptimizationPlan:
        """
        Analyze portfolio for tax optimization opportunities.
        
        Args:
            user_id: User identifier
            portfolio_id: Portfolio identifier
            tax_year: Tax year for analysis (default current year)
            
        Returns:
            TaxOptimizationPlan with opportunities and recommendations
            
        Raises:
            ValueError: If portfolio not found or invalid input
            ClientError: If AWS service calls fail
        """
        if tax_year is None:
            tax_year = datetime.utcnow().year
        
        logger.info(f"Starting tax optimization for user={user_id}, portfolio={portfolio_id}, tax_year={tax_year}")
        
        try:
            # Step 1: Retrieve portfolio data
            portfolio = self._retrieve_portfolio(user_id, portfolio_id)
            logger.info(f"Retrieved portfolio with {len(portfolio.holdings)} holdings")
            
            # Step 2: Retrieve cost basis for all holdings
            cost_basis_data = self._retrieve_cost_basis(user_id, portfolio_id, portfolio)
            logger.info(f"Retrieved cost basis for {len(cost_basis_data)} holdings")
            
            # Step 3: Identify unrealized losses
            tax_loss_opportunities = self._identify_tax_loss_opportunities(portfolio, cost_basis_data)
            logger.info(f"Identified {len(tax_loss_opportunities)} tax loss opportunities")
            
            # Step 4: Calculate potential tax savings
            total_potential_savings = self._calculate_total_tax_savings(tax_loss_opportunities)
            logger.info(f"Total potential tax savings: ${total_potential_savings:.2f}")
            
            # Step 5: Find replacement securities
            recommended_trades = self._find_replacement_securities(tax_loss_opportunities, portfolio)
            logger.info(f"Generated {len(recommended_trades)} recommended trades")
            
            # Step 6: Check wash sale rules
            wash_sale_warnings = self._check_wash_sale_rules(portfolio, recommended_trades)
            logger.info(f"Found {len(wash_sale_warnings)} potential wash sale violations")
            
            # Step 7: Generate Bedrock recommendations
            optimized_trades = self._generate_bedrock_recommendations(
                portfolio,
                tax_loss_opportunities,
                recommended_trades,
                wash_sale_warnings
            )
            logger.info(f"Generated {len(optimized_trades)} optimized trades from Bedrock")
            
            # Step 8: Assemble and return tax optimization plan
            plan = TaxOptimizationPlan(
                portfolio_id=portfolio_id,
                timestamp=datetime.utcnow().isoformat(),
                tax_loss_opportunities=tax_loss_opportunities,
                total_potential_savings=total_potential_savings,
                recommended_trades=optimized_trades,
                wash_sale_warnings=wash_sale_warnings
            )
            
            logger.info(f"Tax optimization complete for portfolio {portfolio_id}")
            return plan
            
        except ValueError as e:
            logger.error(f"Validation error during tax optimization: {str(e)}")
            raise
        except ClientError as e:
            logger.error(f"AWS service error during tax optimization: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during tax optimization: {str(e)}")
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
    
    def _retrieve_cost_basis(self, user_id: str, portfolio_id: str, portfolio: Portfolio) -> Dict[str, CostBasisInfo]:
        """Retrieve cost basis information for all holdings."""
        cost_basis_data = {}
        
        for holding in portfolio.holdings:
            try:
                cost_basis_info = self.cost_basis_tool.execute(user_id, portfolio_id, holding.ticker)
                cost_basis_data[holding.ticker] = cost_basis_info
            except ValueError as e:
                logger.warning(f"Cost basis not found for {holding.ticker}: {str(e)}")
                # Create default cost basis info from holding
                cost_basis_data[holding.ticker] = CostBasisInfo(
                    ticker=holding.ticker,
                    quantity=holding.quantity,
                    cost_per_share=holding.cost_basis,
                    purchase_date=holding.purchase_date
                )
            except ClientError as e:
                logger.warning(f"Error retrieving cost basis for {holding.ticker}: {str(e)}")
                # Continue with other holdings
                continue
        
        return cost_basis_data
    
    def _identify_tax_loss_opportunities(
        self,
        portfolio: Portfolio,
        cost_basis_data: Dict[str, CostBasisInfo]
    ) -> List[TaxLossOpportunity]:
        """Identify securities with unrealized losses."""
        opportunities = []
        
        for holding in portfolio.holdings:
            cost_basis_info = cost_basis_data.get(holding.ticker)
            if not cost_basis_info:
                continue
            
            # Calculate unrealized gain/loss
            cost_basis_total = cost_basis_info.cost_per_share * holding.quantity
            current_value = holding.current_price * holding.quantity
            unrealized_loss = current_value - cost_basis_total
            
            # Only include if there's an unrealized loss
            if unrealized_loss < 0:
                potential_tax_savings = abs(unrealized_loss) * self.tax_rate
                
                opportunity = TaxLossOpportunity(
                    ticker=holding.ticker,
                    quantity=holding.quantity,
                    cost_basis=cost_basis_info.cost_per_share,
                    current_value=current_value,
                    unrealized_loss=unrealized_loss,
                    potential_tax_savings=potential_tax_savings,
                    replacement_security=None
                )
                opportunities.append(opportunity)
        
        return opportunities
    
    def _calculate_total_tax_savings(self, opportunities: List[TaxLossOpportunity]) -> float:
        """Calculate total potential tax savings."""
        return sum(opp.potential_tax_savings for opp in opportunities)
    
    def _find_replacement_securities(
        self,
        opportunities: List[TaxLossOpportunity],
        portfolio: Portfolio
    ) -> List[TaxOptimizedTrade]:
        """Find replacement securities to maintain allocation."""
        trades = []
        
        # Map tickers to asset classes
        asset_class_mapping = {
            "VTI": "stocks",
            "VXUS": "stocks",
            "BND": "bonds",
            "VGIT": "bonds",
            "VMFXX": "cash",
        }
        
        for opportunity in opportunities:
            # Sell the security with loss
            sell_trade = TaxOptimizedTrade(
                action="sell",
                ticker=opportunity.ticker,
                quantity=opportunity.quantity,
                reason=f"Tax-loss harvesting: ${abs(opportunity.unrealized_loss):.2f} loss",
                tax_impact=opportunity.potential_tax_savings
            )
            trades.append(sell_trade)
            
            # Find replacement security in same asset class
            asset_class = asset_class_mapping.get(opportunity.ticker, "other")
            replacement = self._find_similar_security(asset_class, opportunity.ticker, portfolio)
            
            if replacement:
                # Buy replacement security
                buy_trade = TaxOptimizedTrade(
                    action="buy",
                    ticker=replacement,
                    quantity=opportunity.quantity,
                    reason=f"Replacement for {opportunity.ticker} to maintain {asset_class} allocation",
                    tax_impact=0.0
                )
                trades.append(buy_trade)
                
                # Update opportunity with replacement
                opportunity.replacement_security = replacement
        
        return trades
    
    def _find_similar_security(self, asset_class: str, current_ticker: str, portfolio: Portfolio) -> Optional[str]:
        """Find a similar security in the same asset class."""
        # Simple mapping of similar securities
        similar_securities = {
            "VTI": ["VTSAX", "FSKAX"],
            "VXUS": ["VTIAX", "FTIHX"],
            "BND": ["VBTLX", "FXNAX"],
            "VGIT": ["VGSLX", "FXNAX"],
        }
        
        candidates = similar_securities.get(current_ticker, [])
        
        # Return first candidate not already in portfolio
        for candidate in candidates:
            if not any(h.ticker == candidate for h in portfolio.holdings):
                return candidate
        
        return None
    
    def _check_wash_sale_rules(
        self,
        portfolio: Portfolio,
        trades: List[TaxOptimizedTrade]
    ) -> List[WashSaleWarning]:
        """Check for potential wash sale violations."""
        warnings = []
        
        # Get sell trades
        sell_trades = [t for t in trades if t.action == "sell"]
        
        # For each sell trade, check if replacement is purchased within 30 days
        for sell_trade in sell_trades:
            # Find corresponding buy trade
            buy_trades = [t for t in trades if t.action == "buy" and t.ticker != sell_trade.ticker]
            
            if buy_trades:
                # In a real implementation, would check transaction history
                # For now, flag as potential wash sale if buying replacement immediately
                warning = WashSaleWarning(
                    ticker=sell_trade.ticker,
                    sale_date=datetime.utcnow().isoformat(),
                    purchase_date=(datetime.utcnow() + timedelta(days=1)).isoformat(),
                    days_between=1,
                    warning_message=f"Potential wash sale: Selling {sell_trade.ticker} and buying replacement within 30 days"
                )
                warnings.append(warning)
        
        return warnings
    
    def _generate_bedrock_recommendations(
        self,
        portfolio: Portfolio,
        opportunities: List[TaxLossOpportunity],
        trades: List[TaxOptimizedTrade],
        warnings: List[WashSaleWarning],
        session_id: str = "",
    ) -> List[TaxOptimizedTrade]:
        """Generate optimized trades using Bedrock with RAG enrichment."""
        try:
            query = f"Tax-loss harvesting opportunities for portfolio {portfolio.portfolio_name}"
            rag_context = self.rag_enricher.enrich(query, session_id or portfolio.portfolio_id)

            prompt = self._build_tax_optimization_prompt(portfolio, opportunities, trades, warnings)
            if rag_context.has_context:
                prompt = prompt + "\n\n" + rag_context.format_context_block()

            response = self._invoke_bedrock_with_retry(prompt, max_retries=2)
            return self._parse_bedrock_trades(response, trades)

        except Exception as e:
            logger.error(f"Error generating Bedrock recommendations: {str(e)}")
            return trades
    
    def _build_tax_optimization_prompt(
        self,
        portfolio: Portfolio,
        opportunities: List[TaxLossOpportunity],
        trades: List[TaxOptimizedTrade],
        warnings: List[WashSaleWarning]
    ) -> str:
        """Build prompt for Bedrock tax optimization."""
        prompt = f"""Analyze the following portfolio for tax optimization opportunities:

Portfolio: {portfolio.portfolio_name}
Risk Tolerance: {portfolio.risk_tolerance}

Holdings:
"""
        for holding in portfolio.holdings:
            prompt += f"- {holding.ticker}: {holding.quantity} shares @ ${holding.current_price:.2f}\n"
        
        prompt += f"\nTax Loss Harvesting Opportunities ({len(opportunities)} found):\n"
        for opp in opportunities:
            prompt += f"- {opp.ticker}: ${abs(opp.unrealized_loss):.2f} loss, potential tax savings: ${opp.potential_tax_savings:.2f}\n"
        
        prompt += f"\nProposed Trades ({len(trades)} total):\n"
        for trade in trades:
            prompt += f"- {trade.action.upper()} {trade.quantity} shares of {trade.ticker}: {trade.reason}\n"
        
        if warnings:
            prompt += f"\nWash Sale Warnings ({len(warnings)} found):\n"
            for warning in warnings:
                prompt += f"- {warning.warning_message}\n"
        
        prompt += """
Based on this analysis, provide recommendations for optimizing the tax-loss harvesting strategy.
Consider:
1. Which losses should be harvested immediately
2. Which losses should be deferred
3. Optimal replacement securities to maintain allocation
4. Wash sale avoidance strategies

Format your response as a JSON object with the following structure:
{
    "recommended_trades": [
        {
            "action": "sell" or "buy",
            "ticker": "TICKER",
            "quantity": number,
            "reason": "explanation",
            "tax_impact": number
        }
    ],
    "total_tax_savings": number,
    "notes": "additional recommendations"
}"""
        
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
    
    def _parse_bedrock_trades(self, response: str, fallback_trades: List[TaxOptimizedTrade]) -> List[TaxOptimizedTrade]:
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
                trade = TaxOptimizedTrade(
                    action=trade_data.get("action", "sell"),
                    ticker=trade_data.get("ticker", ""),
                    quantity=int(trade_data.get("quantity", 0)),
                    reason=trade_data.get("reason", ""),
                    tax_impact=float(trade_data.get("tax_impact", 0.0))
                )
                trades.append(trade)
            
            return trades if trades else fallback_trades
            
        except Exception as e:
            logger.warning(f"Error parsing Bedrock trades: {str(e)}, using fallback trades")
            return fallback_trades


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for Tax Optimizer Agent.
    
    Expected event structure:
    {
        "user_id": "user_123",
        "portfolio_id": "portfolio_456",
        "tax_year": 2024
    }
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Extract parameters
        user_id = event.get("user_id")
        portfolio_id = event.get("portfolio_id")
        tax_year = event.get("tax_year")
        
        # Validate input
        if not user_id or not portfolio_id:
            raise ValueError("user_id and portfolio_id are required")
        
        # Perform tax optimization
        optimizer = TaxOptimizer()
        plan = optimizer.optimize(user_id, portfolio_id, tax_year)
        
        # Return success response
        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "success",
                "portfolio_id": plan.portfolio_id,
                "timestamp": plan.timestamp,
                "tax_loss_opportunities": [
                    {
                        "ticker": opp.ticker,
                        "quantity": opp.quantity,
                        "cost_basis": opp.cost_basis,
                        "current_value": opp.current_value,
                        "unrealized_loss": opp.unrealized_loss,
                        "potential_tax_savings": opp.potential_tax_savings,
                        "replacement_security": opp.replacement_security
                    }
                    for opp in plan.tax_loss_opportunities
                ],
                "total_potential_savings": plan.total_potential_savings,
                "recommended_trades": [
                    {
                        "action": trade.action,
                        "ticker": trade.ticker,
                        "quantity": trade.quantity,
                        "reason": trade.reason,
                        "tax_impact": trade.tax_impact
                    }
                    for trade in plan.recommended_trades
                ],
                "wash_sale_warnings": [
                    {
                        "ticker": warning.ticker,
                        "sale_date": warning.sale_date,
                        "purchase_date": warning.purchase_date,
                        "days_between": warning.days_between,
                        "warning_message": warning.warning_message
                    }
                    for warning in plan.wash_sale_warnings
                ]
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
