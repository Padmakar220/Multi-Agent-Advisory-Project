"""
Approval Response Handler

Receives user approval/rejection responses and resumes Step Functions workflow.
"""

import json
import os
from typing import Dict, Any

import boto3
from botocore.exceptions import ClientError

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")
stepfunctions = boto3.client("stepfunctions")

# Environment variables
PENDING_APPROVALS_TABLE = os.environ.get("PENDING_APPROVALS_TABLE", "PendingApprovals")


class ApprovalResponseHandler:
    """Handles approval/rejection responses from users."""
    
    def __init__(self):
        """Initialize approval response handler."""
        self.table = dynamodb.Table(PENDING_APPROVALS_TABLE)
    
    def get_pending_approval(self, approval_id: str) -> Dict[str, Any]:
        """
        Retrieve pending approval from DynamoDB.
        
        Args:
            approval_id: Approval ID to retrieve
        
        Returns:
            Pending approval item or None if not found
        """
        try:
            response = self.table.get_item(Key={"approval_id": approval_id})
            return response.get("Item")
        
        except ClientError as e:
            print(f"Error retrieving pending approval: {e}")
            return None
    
    def update_approval_status(
        self,
        approval_id: str,
        status: str,
        feedback: str = ""
    ) -> bool:
        """
        Update approval status in DynamoDB.
        
        Args:
            approval_id: Approval ID to update
            status: New status (approved, rejected, cancelled)
            feedback: User feedback for rejection
        
        Returns:
            True if successful, False otherwise
        """
        try:
            update_expr = "SET #status = :status"
            expr_values = {":status": status}
            
            if feedback:
                update_expr += ", feedback = :feedback"
                expr_values[":feedback"] = feedback
            
            self.table.update_item(
                Key={"approval_id": approval_id},
                UpdateExpression=update_expr,
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues=expr_values
            )
            
            return True
        
        except ClientError as e:
            print(f"Error updating approval status: {e}")
            return False
    
    def resume_workflow(
        self,
        task_token: str,
        approval_status: str,
        feedback: str = ""
    ) -> bool:
        """
        Resume Step Functions workflow with approval status.
        
        Args:
            task_token: Step Functions task token
            approval_status: Approval status (approved, rejected)
            feedback: User feedback for rejection
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Prepare output payload
            output = {
                "approval_status": approval_status,
                "feedback": feedback
            }
            
            if approval_status == "approved":
                # Resume workflow for execution
                stepfunctions.send_task_success(
                    taskToken=task_token,
                    output=json.dumps(output)
                )
            else:
                # Send task failure for rejection
                stepfunctions.send_task_failure(
                    taskToken=task_token,
                    error="APPROVAL_REJECTED",
                    cause=f"User rejected trade plan. Feedback: {feedback}"
                )
            
            return True
        
        except ClientError as e:
            print(f"Error resuming workflow: {e}")
            return False


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for approval response.
    
    Receives user approval/rejection and resumes Step Functions workflow.
    
    Args:
        event: API Gateway event with approval response
        context: Lambda context
    
    Returns:
        Response with status
    """
    try:
        print(f"Received event: {json.dumps(event)}")
        
        # Parse request body
        if isinstance(event.get("body"), str):
            body = json.loads(event["body"])
        else:
            body = event.get("body", {})
        
        approval_id = body.get("approval_id")
        approval_status = body.get("approval_status")  # "approved" or "rejected"
        feedback = body.get("feedback", "")
        
        # Validate input
        if not approval_id or not approval_status:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": "Missing required fields: approval_id, approval_status"
                })
            }
        
        if approval_status not in ["approved", "rejected"]:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": "Invalid approval_status. Must be 'approved' or 'rejected'"
                })
            }
        
        # Initialize handler
        handler = ApprovalResponseHandler()
        
        # Get pending approval
        pending_approval = handler.get_pending_approval(approval_id)
        if not pending_approval:
            return {
                "statusCode": 404,
                "body": json.dumps({
                    "error": f"Approval not found: {approval_id}"
                })
            }
        
        # Update approval status
        updated = handler.update_approval_status(
            approval_id=approval_id,
            status=approval_status,
            feedback=feedback
        )
        if not updated:
            raise RuntimeError("Failed to update approval status")
        
        # Resume workflow
        task_token = pending_approval.get("task_token")
        resumed = handler.resume_workflow(
            task_token=task_token,
            approval_status=approval_status,
            feedback=feedback
        )
        if not resumed:
            raise RuntimeError("Failed to resume workflow")
        
        # Return success response
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": f"Trade plan {approval_status}",
                "approval_id": approval_id,
                "status": approval_status
            })
        }
    
    except Exception as e:
        print(f"Error in lambda_handler: {e}")
        
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "error_code": "APPROVAL_RESPONSE_ERROR"
            })
        }
