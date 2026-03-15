"""
Approval Handler Lambda Function

Presents trade plans to users for approval and stores pending approvals in DynamoDB.
Generates approval payloads with trade details, tax implications, and costs.
"""

import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import boto3
from botocore.exceptions import ClientError

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")
logger_client = boto3.client("logs")

# Environment variables
PENDING_APPROVALS_TABLE = os.environ.get("PENDING_APPROVALS_TABLE", "PendingApprovals")
LOG_GROUP = os.environ.get("LOG_GROUP", "/aws/lambda/approval-handler")


class ApprovalHandler:
    """Handles trade plan approval workflow."""
    
    def __init__(self):
        """Initialize approval handler."""
        self.table = dynamodb.Table(PENDING_APPROVALS_TABLE)
    
    def generate_approval_payload(
        self,
        session_id: str,
        trade_plan: Dict[str, Any],
        tax_implications: Dict[str, float],
        expected_costs: Dict[str, float],
        projected_outcomes: Dict[str, float],
        task_token: str
    ) -> Dict[str, Any]:
        """
        Generate approval payload with trade details, tax implications, and costs.
        
        Args:
            session_id: Session ID for the workflow
            trade_plan: Rebalancing plan with trade orders
            tax_implications: Tax impact details
            expected_costs: Transaction costs breakdown
            projected_outcomes: Expected portfolio outcomes
            task_token: Step Functions task token for resuming workflow
        
        Returns:
            Approval payload dictionary
        """
        # Calculate approval deadline (24 hours from now)
        approval_deadline = (datetime.utcnow() + timedelta(hours=24)).isoformat()
        
        # Generate approval ID
        approval_id = str(uuid.uuid4())
        
        # Build approval payload
        approval_payload = {
            "approval_id": approval_id,
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "approval_deadline": approval_deadline,
            "trade_plan": {
                "trade_orders": trade_plan.get("trade_orders", []),
                "projected_allocation": trade_plan.get("projected_allocation", {})
            },
            "tax_implications": tax_implications,
            "expected_costs": expected_costs,
            "projected_outcomes": projected_outcomes,
            "task_token": task_token,
            "status": "pending_approval"
        }
        
        return approval_payload
    
    def store_pending_approval(self, approval_payload: Dict[str, Any]) -> bool:
        """
        Store pending approval in DynamoDB.
        
        Args:
            approval_payload: Approval payload to store
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Calculate TTL (24 hours from now)
            ttl = int((datetime.utcnow() + timedelta(hours=24)).timestamp())
            
            # Store in DynamoDB
            self.table.put_item(
                Item={
                    "approval_id": approval_payload["approval_id"],
                    "session_id": approval_payload["session_id"],
                    "timestamp": approval_payload["timestamp"],
                    "approval_deadline": approval_payload["approval_deadline"],
                    "trade_plan": json.dumps(approval_payload["trade_plan"]),
                    "tax_implications": json.dumps(approval_payload["tax_implications"]),
                    "projected_outcomes": json.dumps(approval_payload["projected_outcomes"]),
                    "task_token": approval_payload["task_token"],
                    "status": "pending_approval",
                    "ttl": ttl
                }
            )
            
            return True
        
        except ClientError as e:
            print(f"Error storing pending approval: {e}")
            return False
    
    def present_trade_plan(self, approval_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Present trade plan to user for approval.
        
        Args:
            approval_payload: Approval payload with trade details
        
        Returns:
            Response with approval presentation details
        """
        # Extract trade details for presentation
        trade_plan = approval_payload.get("trade_plan", {})
        trade_orders = trade_plan.get("trade_orders", [])
        
        # Build presentation response
        presentation = {
            "approval_id": approval_payload["approval_id"],
            "session_id": approval_payload["session_id"],
            "message": "Trade plan requires your approval",
            "trade_summary": {
                "total_trades": len(trade_orders),
                "buy_orders": len([t for t in trade_orders if t.get("action") == "buy"]),
                "sell_orders": len([t for t in trade_orders if t.get("action") == "sell"]),
                "expected_costs": trade_plan.get("expected_costs", {}),
                "projected_allocation": trade_plan.get("projected_allocation", {})
            },
            "tax_implications": approval_payload.get("tax_implications", {}),
            "projected_outcomes": approval_payload.get("projected_outcomes", {}),
            "approval_deadline": approval_payload["approval_deadline"],
            "trade_details": trade_orders
        }
        
        return presentation


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for approval workflow.
    
    Receives aggregated results from Supervisor Agent, generates approval payload,
    stores pending approval in DynamoDB, and presents trade plan to user.
    
    Args:
        event: Step Functions input with aggregated results
        context: Lambda context
    
    Returns:
        Response with approval presentation details
    """
    try:
        print(f"Received event: {json.dumps(event)}")
        
        # Extract task token from Step Functions
        task_token = event.get("Task", {}).get("Token")
        if not task_token:
            raise ValueError("Task token not found in event")
        
        # Extract workflow data
        session_id = event.get("session_id", str(uuid.uuid4()))
        trade_plan = event.get("trade_plan", {})
        tax_implications = event.get("tax_implications", {})
        expected_costs = event.get("expected_costs", {})
        projected_outcomes = event.get("projected_outcomes", {})
        
        # Initialize approval handler
        handler = ApprovalHandler()
        
        # Generate approval payload
        approval_payload = handler.generate_approval_payload(
            session_id=session_id,
            trade_plan=trade_plan,
            tax_implications=tax_implications,
            expected_costs=expected_costs,
            projected_outcomes=projected_outcomes,
            task_token=task_token
        )
        
        # Store pending approval in DynamoDB
        stored = handler.store_pending_approval(approval_payload)
        if not stored:
            raise RuntimeError("Failed to store pending approval")
        
        # Present trade plan to user
        presentation = handler.present_trade_plan(approval_payload)
        
        # Return presentation response
        return {
            "statusCode": 200,
            "body": json.dumps(presentation)
        }
    
    except Exception as e:
        print(f"Error in lambda_handler: {e}")
        
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "error_code": "APPROVAL_HANDLER_ERROR"
            })
        }
