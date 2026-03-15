"""Portfolio Analyzer Agent Lambda handler."""

import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional

import boto3
from botocore.exceptions import ClientError

from src.models.portfolio import Portfolio
from src.models.responses import (
    AnalysisReport,
    PerformanceMetrics,
    RiskMetrics,
    AllocationDrift,
    MarketInsight,
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


class PortfolioAnalyzer:
    """Portfolio Analyzer Agent for analyzing portfolio performance and risk."""
    
    def __init__(self):
        """Initialize the Portfolio Analyzer."""
        self.portfolio_tool = portfolio_tool
        self.rag_enricher = RAGEnricher()
        self.market_data_tool = market_data_tool
        self.bedrock_client = bedrock_client
    
    def analyze(self, user_id: str, portfolio_id: str, analysis_type: str = "comprehensive") -> AnalysisReport:
        """
        Analyze a portfolio and generate a comprehensive analysis report.
        
        Args:
            user_id: User identifier
            portfolio_id: Portfolio identifier
            analysis_type: Type of analysis ("performance", "risk", "drift", "comprehensive")
            
        Returns:
            AnalysisReport with all metrics and recommendations
            
        Raises:
            ValueError: If portfolio not found or invalid input
            ClientError: If AWS service calls fail
        """
        logger.info(f"Starting portfolio analysis for user={user_id}, portfolio={portfolio_id}, type={analysis_type}")
        
        try:
            # Step 1: Retrieve portfolio data
            portfolio = self._retrieve_portfolio(user_id, portfolio_id)
            logger.info(f"Retrieved portfolio with {len(portfolio.holdings)} holdings")
            
            # Step 2: Calculate performance metrics
            performance_metrics = self._calculate_performance_metrics(portfolio)
            logger.info(f"Calculated performance metrics: total_return={performance_metrics.total_return}")
            
            # Step 3: Calculate risk metrics
            risk_metrics = self._calculate_risk_metrics(portfolio)
            logger.info(f"Calculated risk metrics: volatility={risk_metrics.portfolio_volatility}")
            
            # Step 4: Calculate allocation drift
            allocation_drift = self._calculate_allocation_drift(portfolio)
            logger.info(f"Calculated allocation drift: rebalancing_needed={allocation_drift.rebalancing_needed}")
            
            # Step 5: Query market context
            market_context = self._query_market_context(portfolio)
            logger.info(f"Retrieved {len(market_context)} market insights")
            
            # Step 6: Generate recommendations using Bedrock
            recommendations = self._generate_recommendations(
                portfolio,
                performance_metrics,
                risk_metrics,
                allocation_drift,
                market_context
            )
            logger.info(f"Generated {len(recommendations)} recommendations")
            
            # Step 7: Assemble and return analysis report
            report = AnalysisReport(
                portfolio_id=portfolio_id,
                timestamp=datetime.utcnow().isoformat(),
                performance_metrics=performance_metrics,
                risk_metrics=risk_metrics,
                allocation_drift=allocation_drift,
                market_context=market_context,
                recommendations=recommendations
            )
            
            logger.info(f"Analysis complete for portfolio {portfolio_id}")
            return report
            
        except ValueError as e:
            logger.error(f"Validation error during analysis: {str(e)}")
            raise
        except ClientError as e:
            logger.error(f"AWS service error during analysis: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during analysis: {str(e)}")
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
    
    def _calculate_performance_metrics(self, portfolio: Portfolio) -> PerformanceMetrics:
        """Calculate performance metrics for the portfolio."""
        if not portfolio.holdings:
            # Empty portfolio
            return PerformanceMetrics(
                total_return=0.0,
                annualized_return=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0
            )
        
        # Calculate total return
        total_cost_basis = sum(h.quantity * h.cost_basis for h in portfolio.holdings)
        total_market_value = sum(h.market_value for h in portfolio.holdings)
        
        if total_cost_basis == 0:
            total_return = 0.0
        else:
            total_return = (total_market_value - total_cost_basis) / total_cost_basis
        
        # Simplified calculations (in production, would use historical data)
        annualized_return = total_return  # Placeholder
        sharpe_ratio = 0.0  # Placeholder - would need risk-free rate and historical returns
        max_drawdown = 0.0  # Placeholder - would need historical price data
        
        return PerformanceMetrics(
            total_return=total_return,
            annualized_return=annualized_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown
        )
    
    def _calculate_risk_metrics(self, portfolio: Portfolio) -> RiskMetrics:
        """Calculate risk metrics for the portfolio."""
        if not portfolio.holdings:
            return RiskMetrics(
                portfolio_volatility=0.0,
                beta=1.0,  # Default beta is 1.0 (market beta)
                var_95=0.0,
                concentration_risk={}
            )
        
        # Calculate concentration risk (percentage of portfolio in each holding)
        total_value = sum(h.market_value for h in portfolio.holdings)
        concentration_risk = {}
        
        if total_value > 0:
            for holding in portfolio.holdings:
                concentration = holding.market_value / total_value
                concentration_risk[holding.ticker] = concentration
        
        # Simplified calculations (in production, would use historical data)
        portfolio_volatility = 0.0  # Placeholder
        beta = 1.0  # Placeholder
        var_95 = 0.0  # Placeholder
        
        return RiskMetrics(
            portfolio_volatility=portfolio_volatility,
            beta=beta,
            var_95=var_95,
            concentration_risk=concentration_risk
        )
    
    def _calculate_allocation_drift(self, portfolio: Portfolio) -> AllocationDrift:
        """Calculate allocation drift from target allocation."""
        # Map tickers to asset classes (simplified mapping)
        asset_class_mapping = {
            "VTI": "stocks",
            "VXUS": "stocks",
            "BND": "bonds",
            "VGIT": "bonds",
            "VMFXX": "cash",
        }
        
        # Calculate current allocation
        total_value = sum(h.market_value for h in portfolio.holdings)
        current_allocation = {}
        
        if total_value > 0:
            for holding in portfolio.holdings:
                asset_class = asset_class_mapping.get(holding.ticker, "other")
                if asset_class not in current_allocation:
                    current_allocation[asset_class] = 0.0
                current_allocation[asset_class] += holding.market_value / total_value
        
        # Ensure all asset classes are represented
        for asset_class in portfolio.target_allocation:
            if asset_class not in current_allocation:
                current_allocation[asset_class] = 0.0
        
        # For empty portfolios, set current allocation to match target
        if not portfolio.holdings:
            current_allocation = dict(portfolio.target_allocation)
        
        # Calculate drift
        drift_percentage = {}
        max_drift = 0.0
        
        for asset_class in portfolio.target_allocation:
            current = current_allocation.get(asset_class, 0.0)
            target = portfolio.target_allocation.get(asset_class, 0.0)
            drift = abs(current - target)
            drift_percentage[asset_class] = drift
            max_drift = max(max_drift, drift)
        
        # Determine if rebalancing is needed (threshold: 5% drift)
        rebalancing_needed = max_drift > 0.05
        
        return AllocationDrift(
            current_allocation=current_allocation,
            target_allocation=portfolio.target_allocation,
            drift_percentage=drift_percentage,
            rebalancing_needed=rebalancing_needed
        )
    
    def _query_market_context(self, portfolio: Portfolio) -> list:
        """Query OpenSearch for market context relevant to portfolio."""
        market_context = []
        
        try:
            # Generate queries based on portfolio holdings
            tickers = [h.ticker for h in portfolio.holdings]
            
            for ticker in tickers[:5]:  # Limit to first 5 tickers
                try:
                    results = self.market_data_tool.execute(
                        query=f"Market analysis for {ticker}",
                        filters={"ticker": ticker},
                        top_k=2
                    )
                    
                    for result in results:
                        market_context.append(
                            MarketInsight(
                                title=result.title,
                                content=result.content,
                                ticker=result.ticker,
                                sector=result.sector,
                                timestamp=result.timestamp,
                                source=result.source,
                                relevance_score=result.similarity_score
                            )
                        )
                except Exception as e:
                    logger.warning(f"Error querying market data for {ticker}: {str(e)}")
                    continue
            
        except Exception as e:
            logger.warning(f"Error querying market context: {str(e)}")
            # Continue without market context
        
        return market_context
    
    def _generate_recommendations(
        self,
        portfolio: Portfolio,
        performance_metrics: PerformanceMetrics,
        risk_metrics: RiskMetrics,
        allocation_drift: AllocationDrift,
        market_context: list,
        session_id: str = "",
    ) -> list:
        """Generate recommendations using Bedrock Claude model with RAG enrichment."""
        recommendations = []

        try:
            # RAG enrichment before prompt construction
            query = f"Portfolio analysis for {portfolio.portfolio_name} with holdings: " + \
                    ", ".join(h.ticker for h in portfolio.holdings[:10])
            rag_context = self.rag_enricher.enrich(query, session_id or portfolio.portfolio_id)

            # Build prompt with portfolio context and RAG context
            prompt = self._build_analysis_prompt(
                portfolio,
                performance_metrics,
                risk_metrics,
                allocation_drift,
                market_context,
            )

            # Inject RAG context block before the final instruction
            if rag_context.has_context:
                prompt = prompt + "\n\n" + rag_context.format_context_block()

            # Invoke Bedrock with retry logic
            response = self._invoke_bedrock_with_retry(prompt, max_retries=2)

            # Parse recommendations from response
            recommendations = self._parse_recommendations(response)

        except Exception as e:
            logger.error(f"Error generating recommendations: {str(e)}")
            recommendations = [
                "Review portfolio allocation against target allocation",
                "Consider rebalancing if drift exceeds 5%",
                "Monitor market conditions for significant changes",
            ]

        return recommendations
    
    def _build_analysis_prompt(
        self,
        portfolio: Portfolio,
        performance_metrics: PerformanceMetrics,
        risk_metrics: RiskMetrics,
        allocation_drift: AllocationDrift,
        market_context: list
    ) -> str:
        """Build prompt for Bedrock analysis."""
        prompt = f"""Analyze the following portfolio and provide investment recommendations:

Portfolio: {portfolio.portfolio_name}
Risk Tolerance: {portfolio.risk_tolerance}

Holdings:
"""
        for holding in portfolio.holdings:
            prompt += f"- {holding.ticker}: {holding.quantity} shares @ ${holding.current_price:.2f} (cost basis: ${holding.cost_basis:.2f})\n"
        
        prompt += f"""
Performance Metrics:
- Total Return: {performance_metrics.total_return:.2%}
- Annualized Return: {performance_metrics.annualized_return:.2%}
- Sharpe Ratio: {performance_metrics.sharpe_ratio:.2f}
- Max Drawdown: {performance_metrics.max_drawdown:.2%}

Risk Metrics:
- Portfolio Volatility: {risk_metrics.portfolio_volatility:.2%}
- Beta: {risk_metrics.beta:.2f}
- Value at Risk (95%): {risk_metrics.var_95:.2%}

Allocation Analysis:
Current vs Target:
"""
        for asset_class in allocation_drift.target_allocation:
            current = allocation_drift.current_allocation.get(asset_class, 0.0)
            target = allocation_drift.target_allocation.get(asset_class, 0.0)
            drift = allocation_drift.drift_percentage.get(asset_class, 0.0)
            prompt += f"- {asset_class}: {current:.1%} (target: {target:.1%}, drift: {drift:.1%})\n"
        
        if market_context:
            prompt += "\nMarket Context:\n"
            for insight in market_context[:3]:
                prompt += f"- {insight.title}: {insight.content[:100]}...\n"
        
        prompt += """
Based on this analysis, provide 3-5 specific, actionable investment recommendations. 
Format each recommendation as a single sentence starting with an action verb."""
        
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
                    # Exponential backoff
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
    
    def _parse_recommendations(self, response: str) -> list:
        """Parse recommendations from Bedrock response."""
        recommendations = []
        
        # Split response into lines and extract recommendations
        lines = response.split("\n")
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                # Remove bullet points and numbering
                if line.startswith("-"):
                    line = line[1:].strip()
                elif line[0].isdigit() and "." in line[:3]:
                    line = line.split(".", 1)[1].strip()
                
                if line:
                    recommendations.append(line)
        
        return recommendations[:5]  # Return up to 5 recommendations


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for Portfolio Analyzer Agent.
    
    Expected event structure:
    {
        "user_id": "user_123",
        "portfolio_id": "portfolio_456",
        "analysis_type": "comprehensive"
    }
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Extract parameters
        user_id = event.get("user_id")
        portfolio_id = event.get("portfolio_id")
        analysis_type = event.get("analysis_type", "comprehensive")
        
        # Validate input
        if not user_id or not portfolio_id:
            raise ValueError("user_id and portfolio_id are required")
        
        # Perform analysis
        analyzer = PortfolioAnalyzer()
        report = analyzer.analyze(user_id, portfolio_id, analysis_type)
        
        # Return success response
        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "success",
                "portfolio_id": report.portfolio_id,
                "timestamp": report.timestamp,
                "performance_metrics": {
                    "total_return": report.performance_metrics.total_return,
                    "annualized_return": report.performance_metrics.annualized_return,
                    "sharpe_ratio": report.performance_metrics.sharpe_ratio,
                    "max_drawdown": report.performance_metrics.max_drawdown
                },
                "risk_metrics": {
                    "portfolio_volatility": report.risk_metrics.portfolio_volatility,
                    "beta": report.risk_metrics.beta,
                    "var_95": report.risk_metrics.var_95,
                    "concentration_risk": report.risk_metrics.concentration_risk
                },
                "allocation_drift": {
                    "current_allocation": report.allocation_drift.current_allocation,
                    "target_allocation": report.allocation_drift.target_allocation,
                    "drift_percentage": report.allocation_drift.drift_percentage,
                    "rebalancing_needed": report.allocation_drift.rebalancing_needed
                },
                "market_context_count": len(report.market_context),
                "recommendations": report.recommendations
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
