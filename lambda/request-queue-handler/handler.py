"""
Request Queue Handler - Manages request queueing when Lambda capacity is exhausted.

This Lambda function:
1. Receives requests when agent capacity is reached
2. Queues them in SQS for later processing
3. Notifies users of expected wait time
4. Monitors queue depth and processes queued requests
"""

import json
import boto3
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import uuid

# Initialize AWS clients
sqs_client = boto3.client('sqs')
lambda_client = boto3.client('lambda')
dynamodb = boto3.resource('dynamodb')
sns_client = boto3.client('sns')

# Environment variables
REQUEST_QUEUE_URL = os.environ.get('REQUEST_QUEUE_URL')
DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE', 'advisory-agent-sessions')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')
AGENT_LAMBDA_ARN = os.environ.get('AGENT_LAMBDA_ARN')

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


class RequestQueueManager:
    """Manages request queueing and capacity overflow handling."""

    def __init__(self):
        self.queue_url = REQUEST_QUEUE_URL
        self.table = dynamodb.Table(DYNAMODB_TABLE)

    def queue_request(self, request: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """
        Queue a request when Lambda capacity is exhausted.

        Args:
            request: The original request payload
            user_id: User ID for notification

        Returns:
            Response with queue position and estimated wait time
        """
        try:
            # Generate unique request ID
            request_id = str(uuid.uuid4())

            # Calculate estimated wait time based on queue depth
            queue_depth = self._get_queue_depth()
            estimated_wait_seconds = self._calculate_wait_time(queue_depth)

            # Add request to SQS queue
            message_body = {
                'request_id': request_id,
                'user_id': user_id,
                'original_request': request,
                'queued_at': datetime.utcnow().isoformat(),
                'queue_position': queue_depth + 1,
                'estimated_wait_seconds': estimated_wait_seconds
            }

            response = sqs_client.send_message(
                QueueUrl=self.queue_url,
                MessageBody=json.dumps(message_body),
                MessageAttributes={
                    'user_id': {'StringValue': user_id, 'DataType': 'String'},
                    'request_id': {'StringValue': request_id, 'DataType': 'String'},
                    'priority': {'StringValue': 'normal', 'DataType': 'String'}
                }
            )

            logger.info(
                f"Request queued successfully",
                extra={
                    'request_id': request_id,
                    'user_id': user_id,
                    'queue_position': queue_depth + 1,
                    'estimated_wait_seconds': estimated_wait_seconds
                }
            )

            # Notify user of queueing
            self._notify_user_queued(
                user_id,
                request_id,
                queue_depth + 1,
                estimated_wait_seconds
            )

            return {
                'status': 'queued',
                'request_id': request_id,
                'queue_position': queue_depth + 1,
                'estimated_wait_seconds': estimated_wait_seconds,
                'message': f'Your request has been queued. Expected wait time: {estimated_wait_seconds} seconds'
            }

        except Exception as e:
            logger.error(f"Error queueing request: {str(e)}", exc_info=True)
            raise

    def process_queued_requests(self) -> Dict[str, Any]:
        """
        Process queued requests from SQS.

        Returns:
            Summary of processed requests
        """
        processed_count = 0
        failed_count = 0
        results = []

        try:
            while True:
                # Receive messages from queue
                messages = sqs_client.receive_message(
                    QueueUrl=self.queue_url,
                    MaxNumberOfMessages=10,
                    WaitTimeSeconds=1,
                    MessageAttributeNames=['All']
                )

                if 'Messages' not in messages:
                    break

                for message in messages['Messages']:
                    try:
                        # Parse message body
                        body = json.loads(message['Body'])
                        request_id = body['request_id']
                        user_id = body['user_id']
                        original_request = body['original_request']

                        # Attempt to process request
                        result = self._process_single_request(original_request, user_id)

                        if result.get('success'):
                            processed_count += 1
                            results.append({
                                'request_id': request_id,
                                'status': 'processed',
                                'result': result
                            })

                            # Delete message from queue
                            sqs_client.delete_message(
                                QueueUrl=self.queue_url,
                                ReceiptHandle=message['ReceiptHandle']
                            )

                            logger.info(
                                f"Queued request processed successfully",
                                extra={'request_id': request_id, 'user_id': user_id}
                            )
                        else:
                            # Message will be retried (visibility timeout)
                            failed_count += 1
                            logger.warning(
                                f"Failed to process queued request",
                                extra={'request_id': request_id, 'user_id': user_id}
                            )

                    except Exception as e:
                        failed_count += 1
                        logger.error(
                            f"Error processing queued message: {str(e)}",
                            exc_info=True
                        )

            return {
                'processed_count': processed_count,
                'failed_count': failed_count,
                'results': results
            }

        except Exception as e:
            logger.error(f"Error processing queued requests: {str(e)}", exc_info=True)
            raise

    def _get_queue_depth(self) -> int:
        """Get approximate number of messages in queue."""
        try:
            response = sqs_client.get_queue_attributes(
                QueueUrl=self.queue_url,
                AttributeNames=['ApproximateNumberOfMessages']
            )
            return int(response['Attributes']['ApproximateNumberOfMessages'])
        except Exception as e:
            logger.warning(f"Error getting queue depth: {str(e)}")
            return 0

    def _calculate_wait_time(self, queue_depth: int) -> int:
        """
        Calculate estimated wait time based on queue depth.

        Assumes average processing time of 5 seconds per request.
        """
        # Average processing time per request (seconds)
        avg_processing_time = 5

        # Concurrent processing capacity (number of workers)
        concurrent_capacity = 10

        # Calculate wait time
        wait_time = max(0, (queue_depth * avg_processing_time) // concurrent_capacity)

        return wait_time

    def _process_single_request(self, request: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """
        Process a single queued request.

        Args:
            request: The request payload
            user_id: User ID

        Returns:
            Processing result
        """
        try:
            # Invoke the appropriate agent Lambda based on request type
            request_type = request.get('request_type', 'analyze')

            # Map request type to Lambda function
            lambda_mapping = {
                'analyze': 'portfolio-analyzer',
                'tax_optimize': 'tax-optimizer',
                'rebalance': 'rebalancing-agent'
            }

            function_name = lambda_mapping.get(request_type, 'supervisor-agent')

            # Invoke Lambda function
            response = lambda_client.invoke(
                FunctionName=function_name,
                InvocationType='RequestResponse',
                Payload=json.dumps(request)
            )

            # Parse response
            if response['StatusCode'] == 200:
                payload = json.loads(response['Payload'].read())
                return {
                    'success': True,
                    'result': payload
                }
            else:
                return {
                    'success': False,
                    'error': f"Lambda returned status {response['StatusCode']}"
                }

        except Exception as e:
            logger.error(f"Error processing request: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }

    def _notify_user_queued(
        self,
        user_id: str,
        request_id: str,
        queue_position: int,
        estimated_wait_seconds: int
    ) -> None:
        """
        Notify user that their request has been queued.

        Args:
            user_id: User ID
            request_id: Request ID
            queue_position: Position in queue
            estimated_wait_seconds: Estimated wait time
        """
        try:
            if not SNS_TOPIC_ARN:
                logger.warning("SNS_TOPIC_ARN not configured, skipping notification")
                return

            message = f"""
Your portfolio management request has been queued due to high system load.

Request ID: {request_id}
Queue Position: {queue_position}
Estimated Wait Time: {estimated_wait_seconds} seconds

We will process your request as soon as capacity becomes available.
You will receive a notification when your request is being processed.
            """

            sns_client.publish(
                TopicArn=SNS_TOPIC_ARN,
                Subject='Your Portfolio Request Has Been Queued',
                Message=message
            )

            logger.info(
                f"User notification sent",
                extra={
                    'user_id': user_id,
                    'request_id': request_id,
                    'queue_position': queue_position
                }
            )

        except Exception as e:
            logger.error(f"Error sending user notification: {str(e)}", exc_info=True)


def lambda_handler(event, context):
    """
    Lambda handler for request queueing.

    Supports two modes:
    1. Queue a new request (when capacity is exhausted)
    2. Process queued requests (triggered by EventBridge or manual invocation)
    """
    try:
        manager = RequestQueueManager()

        # Determine operation mode
        operation = event.get('operation', 'queue')

        if operation == 'queue':
            # Queue a new request
            user_id = event.get('user_id')
            request = event.get('request')

            if not user_id or not request:
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'Missing required fields: user_id, request'
                    })
                }

            result = manager.queue_request(request, user_id)

            return {
                'statusCode': 202,
                'body': json.dumps(result)
            }

        elif operation == 'process':
            # Process queued requests
            result = manager.process_queued_requests()

            return {
                'statusCode': 200,
                'body': json.dumps(result)
            }

        else:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': f'Unknown operation: {operation}'
                })
            }

    except Exception as e:
        logger.error(f"Error in lambda_handler: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal server error',
                'message': str(e)
            })
        }
