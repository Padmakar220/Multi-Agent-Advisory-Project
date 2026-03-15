# Network Stack Documentation

## Overview

The network stack (`network-stack.yaml`) creates the foundational network infrastructure for the Multi-Agent Advisory AI System. This includes VPC, subnets, NAT gateways, security groups, and VPC endpoints for secure, private communication with AWS services.

## Architecture

### VPC Configuration
- **CIDR Block**: 10.0.0.0/16 (default, configurable)
- **DNS Support**: Enabled
- **DNS Hostnames**: Enabled

### Subnets

#### Public Subnets (2 AZs)
- **Public Subnet 1**: 10.0.1.0/24 (AZ1)
- **Public Subnet 2**: 10.0.2.0/24 (AZ2)
- **Purpose**: Host NAT Gateways for private subnet internet access
- **Internet Access**: Via Internet Gateway

#### Private Subnets (2 AZs)
- **Private Subnet 1**: 10.0.11.0/24 (AZ1)
- **Private Subnet 2**: 10.0.12.0/24 (AZ2)
- **Purpose**: Host Lambda functions and other compute resources
- **Internet Access**: Via NAT Gateways in public subnets

### High Availability

The network is designed for high availability:
- Resources distributed across 2 Availability Zones
- Separate NAT Gateway in each AZ for redundancy
- Independent route tables per private subnet

### NAT Gateways

Two NAT Gateways provide outbound internet connectivity for private subnets:
- **NAT Gateway 1**: In Public Subnet 1 (AZ1)
- **NAT Gateway 2**: In Public Subnet 2 (AZ2)

Each NAT Gateway has a dedicated Elastic IP address.

### Security Groups

#### Lambda Security Group
- **Purpose**: Applied to all Lambda functions
- **Ingress**: None (Lambda functions don't accept inbound connections)
- **Egress**: HTTPS (443) to 0.0.0.0/0 for AWS service access

#### VPC Endpoint Security Group
- **Purpose**: Applied to VPC interface endpoints
- **Ingress**: HTTPS (443) from Lambda Security Group
- **Egress**: None required

### VPC Endpoints

VPC endpoints enable private connectivity to AWS services without traversing the internet, improving security and reducing data transfer costs.

#### Gateway Endpoints (No Additional Charge)
1. **S3 Gateway Endpoint**
   - Service: `com.amazonaws.{region}.s3`
   - Type: Gateway
   - Attached to private route tables

2. **DynamoDB Gateway Endpoint**
   - Service: `com.amazonaws.{region}.dynamodb`
   - Type: Gateway
   - Attached to private route tables

#### Interface Endpoints (Charged per hour + data transfer)
1. **Bedrock Runtime**
   - Service: `com.amazonaws.{region}.bedrock-runtime`
   - Type: Interface
   - Private DNS: Enabled

2. **Bedrock Agent Runtime**
   - Service: `com.amazonaws.{region}.bedrock-agent-runtime`
   - Type: Interface
   - Private DNS: Enabled

3. **CloudWatch Logs**
   - Service: `com.amazonaws.{region}.logs`
   - Type: Interface
   - Private DNS: Enabled

4. **CloudWatch Monitoring**
   - Service: `com.amazonaws.{region}.monitoring`
   - Type: Interface
   - Private DNS: Enabled

5. **Secrets Manager**
   - Service: `com.amazonaws.{region}.secretsmanager`
   - Type: Interface
   - Private DNS: Enabled

6. **STS (Security Token Service)**
   - Service: `com.amazonaws.{region}.sts`
   - Type: Interface
   - Private DNS: Enabled

## Security Features

### Network Isolation
- Lambda functions run in private subnets with no direct internet access
- All AWS service communication via VPC endpoints (private connectivity)
- Security groups enforce least-privilege access

### Data in Transit Encryption
- All VPC endpoints use TLS 1.3 for encrypted communication
- Satisfies Requirement 13.3: "THE System SHALL encrypt all data in transit using TLS 1.3"

### Defense in Depth
- Multiple layers of network security
- Security groups at both Lambda and VPC endpoint levels
- No public IP addresses assigned to Lambda functions

## Deployment

### Prerequisites
- AWS CLI installed and configured
- Appropriate IAM permissions for CloudFormation, VPC, EC2
- Target AWS region supports all required services

### Deploy Using Script

```bash
cd infrastructure
./deploy-network.sh [environment-name]
```

**Examples:**
```bash
# Deploy with default environment name (advisory)
./deploy-network.sh

# Deploy for development
./deploy-network.sh advisory-dev

# Deploy for production
./deploy-network.sh advisory-prod
```

### Deploy Using AWS CLI

```bash
aws cloudformation create-stack \
  --stack-name advisory-network \
  --template-body file://network-stack.yaml \
  --parameters ParameterKey=EnvironmentName,ParameterValue=advisory \
  --region us-east-1
```

### Custom CIDR Blocks

To use custom CIDR blocks:

```bash
aws cloudformation create-stack \
  --stack-name advisory-network \
  --template-body file://network-stack.yaml \
  --parameters \
    ParameterKey=EnvironmentName,ParameterValue=advisory \
    ParameterKey=VpcCIDR,ParameterValue=172.16.0.0/16 \
    ParameterKey=PublicSubnet1CIDR,ParameterValue=172.16.1.0/24 \
    ParameterKey=PublicSubnet2CIDR,ParameterValue=172.16.2.0/24 \
    ParameterKey=PrivateSubnet1CIDR,ParameterValue=172.16.11.0/24 \
    ParameterKey=PrivateSubnet2CIDR,ParameterValue=172.16.12.0/24 \
  --region us-east-1
```

## Stack Outputs

The stack exports the following outputs for use by other stacks:

| Output | Description | Export Name |
|--------|-------------|-------------|
| VPCId | VPC identifier | `{environment}-vpc-id` |
| VPCCidrBlock | VPC CIDR block | `{environment}-vpc-cidr` |
| PublicSubnet1Id | Public subnet 1 ID | `{environment}-public-subnet-1` |
| PublicSubnet2Id | Public subnet 2 ID | `{environment}-public-subnet-2` |
| PrivateSubnet1Id | Private subnet 1 ID | `{environment}-private-subnet-1` |
| PrivateSubnet2Id | Private subnet 2 ID | `{environment}-private-subnet-2` |
| PrivateSubnetIds | Comma-separated private subnet IDs | `{environment}-private-subnets` |
| LambdaSecurityGroupId | Lambda security group ID | `{environment}-lambda-sg-id` |
| VPCEndpointSecurityGroupId | VPC endpoint security group ID | `{environment}-vpc-endpoint-sg-id` |

### Using Outputs in Other Stacks

```yaml
# Example: Reference VPC ID in compute stack
Resources:
  MyLambdaFunction:
    Type: AWS::Lambda::Function
    Properties:
      VpcConfig:
        SubnetIds:
          - Fn::ImportValue: !Sub ${EnvironmentName}-private-subnet-1
          - Fn::ImportValue: !Sub ${EnvironmentName}-private-subnet-2
        SecurityGroupIds:
          - Fn::ImportValue: !Sub ${EnvironmentName}-lambda-sg-id
```

## Cost Considerations

### Fixed Costs
- **NAT Gateways**: ~$0.045/hour per NAT Gateway × 2 = ~$65/month
- **Elastic IPs**: Free when attached to running NAT Gateways
- **Interface VPC Endpoints**: ~$0.01/hour per endpoint × 6 = ~$43/month

### Variable Costs
- **NAT Gateway Data Transfer**: $0.045/GB processed
- **VPC Endpoint Data Transfer**: $0.01/GB processed

### Cost Optimization Tips
1. Use VPC endpoints instead of NAT Gateway for AWS service traffic (saves data transfer costs)
2. Consider removing Secrets Manager and STS endpoints if not heavily used
3. For development environments, consider using a single NAT Gateway

## Troubleshooting

### Stack Creation Fails

**Issue**: Stack creation fails with "The maximum number of VPCs has been reached"
**Solution**: Delete unused VPCs or request a limit increase

**Issue**: Interface endpoint creation fails
**Solution**: Verify the service is available in your region

### Lambda Functions Can't Access AWS Services

**Issue**: Lambda functions timeout when calling AWS services
**Solution**: 
1. Verify Lambda is in private subnets
2. Check security group allows HTTPS egress
3. Verify VPC endpoints are created and healthy
4. Check route tables are correctly configured

### High NAT Gateway Costs

**Issue**: NAT Gateway data transfer costs are high
**Solution**: 
1. Verify VPC endpoints are being used (check VPC endpoint metrics)
2. Review Lambda function traffic patterns
3. Consider consolidating to single NAT Gateway for dev/test

## Validation

After deployment, validate the network configuration:

```bash
# Check VPC endpoints are available
aws ec2 describe-vpc-endpoints \
  --filters "Name=vpc-id,Values=<vpc-id>" \
  --query 'VpcEndpoints[*].[ServiceName,State]' \
  --output table

# Check NAT Gateways are available
aws ec2 describe-nat-gateways \
  --filter "Name=vpc-id,Values=<vpc-id>" \
  --query 'NatGateways[*].[NatGatewayId,State]' \
  --output table

# Check security groups
aws ec2 describe-security-groups \
  --filters "Name=vpc-id,Values=<vpc-id>" \
  --query 'SecurityGroups[*].[GroupName,GroupId]' \
  --output table
```

## Cleanup

To delete the network stack:

```bash
aws cloudformation delete-stack \
  --stack-name advisory-network \
  --region us-east-1
```

**Warning**: Ensure all dependent resources (Lambda functions, etc.) are deleted first, or the stack deletion will fail.

## Related Documentation

- [AWS VPC Documentation](https://docs.aws.amazon.com/vpc/)
- [VPC Endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints.html)
- [NAT Gateways](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-nat-gateway.html)
- [Security Groups](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_SecurityGroups.html)

## Requirements Satisfied

This network stack satisfies the following requirements:

- **Requirement 13.3**: Data encryption in transit using TLS 1.3 (via VPC endpoints)
- **Requirement 13.5**: User data isolation (network-level isolation via VPC)
- **Design Section**: Network Security VPC Configuration
