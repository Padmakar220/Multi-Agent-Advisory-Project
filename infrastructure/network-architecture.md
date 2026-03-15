# Network Architecture Diagram

## Visual Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AWS Cloud (Region)                              │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    VPC (10.0.0.0/16)                                   │ │
│  │                                                                        │ │
│  │  ┌──────────────────────────┐    ┌──────────────────────────┐        │ │
│  │  │  Availability Zone 1     │    │  Availability Zone 2     │        │ │
│  │  │                          │    │                          │        │ │
│  │  │  ┌────────────────────┐  │    │  ┌────────────────────┐  │        │ │
│  │  │  │  Public Subnet 1   │  │    │  │  Public Subnet 2   │  │        │ │
│  │  │  │  10.0.1.0/24       │  │    │  │  10.0.2.0/24       │  │        │ │
│  │  │  │                    │  │    │  │                    │  │        │ │
│  │  │  │  ┌──────────────┐  │  │    │  │  ┌──────────────┐  │  │        │ │
│  │  │  │  │ NAT Gateway  │  │  │    │  │  │ NAT Gateway  │  │  │        │ │
│  │  │  │  │   + EIP      │  │  │    │  │  │   + EIP      │  │  │        │ │
│  │  │  │  └──────┬───────┘  │  │    │  │  └──────┬───────┘  │  │        │ │
│  │  │  └─────────┼──────────┘  │    │  └─────────┼──────────┘  │        │ │
│  │  │            │             │    │            │             │        │ │
│  │  │  ┌─────────┼──────────┐  │    │  ┌─────────┼──────────┐  │        │ │
│  │  │  │  Private Subnet 1  │  │    │  │  Private Subnet 2  │  │        │ │
│  │  │  │  10.0.11.0/24      │  │    │  │  10.0.12.0/24      │  │        │ │
│  │  │  │                    │  │    │  │                    │  │        │ │
│  │  │  │  ┌──────────────┐  │  │    │  │  ┌──────────────┐  │  │        │ │
│  │  │  │  │   Lambda     │  │  │    │  │  │   Lambda     │  │  │        │ │
│  │  │  │  │  Functions   │  │  │    │  │  │  Functions   │  │  │        │ │
│  │  │  │  └──────┬───────┘  │  │    │  │  └──────┬───────┘  │  │        │ │
│  │  │  │         │          │  │    │  │         │          │  │        │ │
│  │  │  │         │          │  │    │  │         │          │  │        │ │
│  │  │  │    ┌────▼────────┐ │  │    │  │    ┌────▼────────┐ │  │        │ │
│  │  │  │    │VPC Endpoints│ │  │    │  │    │VPC Endpoints│ │  │        │ │
│  │  │  │    │ (Interface) │ │  │    │  │    │ (Interface) │ │  │        │ │
│  │  │  │    └─────────────┘ │  │    │  │    └─────────────┘ │  │        │ │
│  │  │  └────────────────────┘  │    │  └────────────────────┘  │        │ │
│  │  └──────────────────────────┘    └──────────────────────────┘        │ │
│  │                                                                        │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐ │ │
│  │  │                    Internet Gateway                              │ │ │
│  │  └────────────────────────────┬─────────────────────────────────────┘ │ │
│  │                               │                                        │ │
│  │  ┌────────────────────────────┴─────────────────────────────────────┐ │ │
│  │  │              VPC Gateway Endpoints (S3, DynamoDB)                │ │ │
│  │  └──────────────────────────────────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                         AWS Services (Private)                         │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐              │ │
│  │  │ Bedrock  │  │DynamoDB  │  │    S3    │  │CloudWatch│              │ │
│  │  │ Runtime  │  │          │  │          │  │   Logs   │              │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘              │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Traffic Flow

### Lambda to AWS Services (via VPC Endpoints)

```
┌─────────────┐
│   Lambda    │
│  Function   │
│ (Private    │
│  Subnet)    │
└──────┬──────┘
       │
       │ HTTPS (443)
       │ TLS 1.3
       │
       ▼
┌──────────────┐
│   Lambda     │
│  Security    │
│   Group      │
│ (Egress 443) │
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│  VPC Endpoint    │
│  Security Group  │
│ (Ingress from    │
│  Lambda SG)      │
└──────┬───────────┘
       │
       ├─────────────► Bedrock Runtime (Interface Endpoint)
       │
       ├─────────────► Bedrock Agent Runtime (Interface Endpoint)
       │
       ├─────────────► CloudWatch Logs (Interface Endpoint)
       │
       ├─────────────► CloudWatch Monitoring (Interface Endpoint)
       │
       ├─────────────► Secrets Manager (Interface Endpoint)
       │
       ├─────────────► STS (Interface Endpoint)
       │
       ├─────────────► DynamoDB (Gateway Endpoint)
       │
       └─────────────► S3 (Gateway Endpoint)
```

### Lambda to Internet (via NAT Gateway)

```
┌─────────────┐
│   Lambda    │
│  Function   │
│ (Private    │
│  Subnet)    │
└──────┬──────┘
       │
       │ HTTPS (443)
       │
       ▼
┌──────────────┐
│   Private    │
│ Route Table  │
│ (0.0.0.0/0   │
│  → NAT GW)   │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│     NAT      │
│   Gateway    │
│  (Public     │
│   Subnet)    │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   Internet   │
│   Gateway    │
└──────┬───────┘
       │
       ▼
    Internet
(External APIs,
 Brokerage APIs)
```

## Security Layers

### Layer 1: Network Isolation
- Lambda functions in private subnets (no public IPs)
- No direct internet access
- All traffic routed through NAT Gateway or VPC Endpoints

### Layer 2: Security Groups
- **Lambda Security Group**: Only allows HTTPS egress
- **VPC Endpoint Security Group**: Only allows HTTPS ingress from Lambda SG
- Stateful firewall rules

### Layer 3: VPC Endpoints
- Private connectivity to AWS services
- No internet traversal
- TLS 1.3 encryption enforced

### Layer 4: IAM Policies
- Lambda execution roles control service access
- Least privilege principle
- Resource-based policies on AWS services

## Resource Relationships

```
VPC
├── Internet Gateway
│   └── Attached to VPC
│
├── Public Subnets (2)
│   ├── Public Subnet 1 (AZ1)
│   │   └── NAT Gateway 1
│   │       └── Elastic IP 1
│   └── Public Subnet 2 (AZ2)
│       └── NAT Gateway 2
│           └── Elastic IP 2
│
├── Private Subnets (2)
│   ├── Private Subnet 1 (AZ1)
│   │   ├── Lambda Functions
│   │   └── VPC Interface Endpoints
│   └── Private Subnet 2 (AZ2)
│       ├── Lambda Functions
│       └── VPC Interface Endpoints
│
├── Route Tables
│   ├── Public Route Table
│   │   ├── 0.0.0.0/0 → Internet Gateway
│   │   └── Associated with Public Subnets
│   ├── Private Route Table 1
│   │   ├── 0.0.0.0/0 → NAT Gateway 1
│   │   └── Associated with Private Subnet 1
│   └── Private Route Table 2
│       ├── 0.0.0.0/0 → NAT Gateway 2
│       └── Associated with Private Subnet 2
│
├── Security Groups
│   ├── Lambda Security Group
│   │   └── Egress: 443 → 0.0.0.0/0
│   └── VPC Endpoint Security Group
│       └── Ingress: 443 ← Lambda SG
│
└── VPC Endpoints
    ├── Gateway Endpoints
    │   ├── S3 (attached to private route tables)
    │   └── DynamoDB (attached to private route tables)
    └── Interface Endpoints
        ├── Bedrock Runtime (in private subnets)
        ├── Bedrock Agent Runtime (in private subnets)
        ├── CloudWatch Logs (in private subnets)
        ├── CloudWatch Monitoring (in private subnets)
        ├── Secrets Manager (in private subnets)
        └── STS (in private subnets)
```

## IP Address Allocation

| Resource | CIDR Block | Available IPs | Purpose |
|----------|------------|---------------|---------|
| VPC | 10.0.0.0/16 | 65,536 | Entire network |
| Public Subnet 1 | 10.0.1.0/24 | 251 | NAT Gateway (AZ1) |
| Public Subnet 2 | 10.0.2.0/24 | 251 | NAT Gateway (AZ2) |
| Private Subnet 1 | 10.0.11.0/24 | 251 | Lambda, VPC Endpoints (AZ1) |
| Private Subnet 2 | 10.0.12.0/24 | 251 | Lambda, VPC Endpoints (AZ2) |

**Note**: AWS reserves 5 IP addresses per subnet (first 4 and last 1), so actual available IPs = 256 - 5 = 251

## High Availability Design

### Multi-AZ Deployment
- All resources deployed across 2 Availability Zones
- Independent failure domains
- Automatic failover for Lambda functions

### NAT Gateway Redundancy
- Separate NAT Gateway per AZ
- If one AZ fails, other AZ continues operating
- No single point of failure

### VPC Endpoint Redundancy
- Interface endpoints span multiple AZs
- Automatic failover built into AWS service
- Gateway endpoints are highly available by design

## Cost Breakdown (Estimated Monthly)

| Resource | Quantity | Unit Cost | Monthly Cost |
|----------|----------|-----------|--------------|
| NAT Gateway | 2 | $0.045/hour | ~$65 |
| NAT Gateway Data | Variable | $0.045/GB | Variable |
| Interface Endpoints | 6 | $0.01/hour | ~$43 |
| Endpoint Data Transfer | Variable | $0.01/GB | Variable |
| Gateway Endpoints | 2 | Free | $0 |
| VPC, Subnets, IGW | - | Free | $0 |
| **Total Fixed** | - | - | **~$108/month** |

**Cost Optimization**: VPC endpoints reduce NAT Gateway data transfer costs by routing AWS service traffic privately.

## Deployment Checklist

- [ ] AWS CLI configured with appropriate credentials
- [ ] Target region supports all required services
- [ ] IAM permissions for CloudFormation, VPC, EC2
- [ ] Bedrock model access enabled in region
- [ ] Review and adjust CIDR blocks if needed
- [ ] Validate CloudFormation template
- [ ] Deploy network stack
- [ ] Verify VPC endpoints are available
- [ ] Verify NAT Gateways are active
- [ ] Test Lambda connectivity to AWS services
- [ ] Review CloudWatch logs for errors
- [ ] Proceed to data stack deployment
