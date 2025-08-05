# VectorDB Function

[![CI](https://github.com/crossplane/function-template-python/actions/workflows/ci.yml/badge.svg)](https://github.com/crossplane/function-template-go/actions/workflows/ci.yml)

A Crossplane composition function for generating AWS vector database infrastructure using Aurora PostgreSQL.

## Overview

This function generates complete AWS infrastructure for hosting vector databases, including:

- **VPC** with configurable CIDR block
- **Internet Gateway** for public access
- **Database Subnets** (3 AZs) with proper CIDR allocation
- **Route Table** with IGW routes for public database access
- **Security Group** allowing PostgreSQL access (port 5432)
- **Subnet Group** for RDS
- **Aurora PostgreSQL Cluster** with proper configuration

## Architecture

The function creates a minimal but production-ready infrastructure for vector databases:

```
Internet → Internet Gateway → Database Subnets → Aurora PostgreSQL Cluster
```

### Key Features

- **Public Database Access**: Database subnets are connected directly to Internet Gateway
- **Multi-AZ Deployment**: Resources distributed across 3 availability zones
- **Security**: PostgreSQL port (5432) open from 0.0.0.0/0 with encryption enabled
- **Scalability**: Aurora Serverless v2 with configurable capacity
- **Backup & Recovery**: Configurable backup retention and maintenance windows

## Prerequisites

### AWS Provider Configuration

Before using this function, you need to configure the AWS provider in Crossplane:

```yaml
apiVersion: aws.upbound.io/v1beta1
kind: ProviderConfig
metadata:
  name: aws-provider-config
spec:
  credentials:
    source: Secret
    secretRef:
      namespace: crossplane-system
      name: aws-creds
      key: creds
```

Create the AWS credentials secret:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: aws-creds
  namespace: crossplane-system
type: Opaque
stringData:
  creds: |
    [default]
    aws_access_key_id = YOUR_ACCESS_KEY
    aws_secret_access_key = YOUR_SECRET_KEY
    aws_region = us-west-2
```

## Usage

### 1. Create a VectorDBClaim

```yaml
apiVersion: db.amazee.ai/v1alpha1
kind: VectorDBClaim
metadata:
  name: my-vectordb
  namespace: my-namespace
spec:
  # Required parameter - AWS region
  location: us-west-2

  # AWS Provider Configuration
  providerConfigRef: "aws-provider-config"

  # Optional parameters with defaults
  envSuffix: "prod"
  engineVersion: "16.1"
  minCapacity: 1.0
  maxCapacity: 32.0
  masterUsername: "postgres"
  backupRetentionPeriod: 30
  backupWindow: "06:42-07:12"
  maintenanceWindow: "wed:04:35-wed:05:05"
  deletionProtection: true
```

### 2. Apply the Composition

```yaml
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: vectordb
spec:
  compositeTypeRef:
    apiVersion: db.amazee.ai/v1alpha1
    kind: VectorDBClaim
  mode: Pipeline
  pipeline:
  - step: generate-vectordb-infrastructure
    functionRef:
      name: vectordb-function
    input:
      apiVersion: vectordb.fn.crossplane.io/v1beta1
      kind: Input
      vpc_cidr: "10.10.0.0/16"
      environment_suffix: "{{ .spec.envSuffix }}"
      master_username: "{{ .spec.masterUsername }}"
      postgres_cluster_name: "vectordb-{{ .metadata.name }}"
      az_count: 3
      engine_version: "{{ .spec.engineVersion }}"
      postgres_cluster_min_capacity: "{{ .spec.minCapacity }}"
      postgres_cluster_max_capacity: "{{ .spec.maxCapacity }}"
      backup_retention_period: "{{ .spec.backupRetentionPeriod }}"
      deletion_protection: "{{ .spec.deletionProtection }}"
```

## Configuration Options

### Required Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `location` | string | AWS region for deployment | `us-west-2` |
| `providerConfigRef` | string | AWS provider configuration name | `aws-provider-config` |

### Optional Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `envSuffix` | string | `"dev"` | Environment suffix for resource naming |
| `engineVersion` | string | `"16.1"` | Aurora PostgreSQL engine version |
| `minCapacity` | float | `0.5` | Minimum Aurora Serverless v2 capacity (ACUs) |
| `maxCapacity` | float | `16.0` | Maximum Aurora Serverless v2 capacity (ACUs) |
| `masterUsername` | string | `"postgres"` | Master database username |
| `backupRetentionPeriod` | int | `7` | Backup retention period in days |
| `backupWindow` | string | `"06:42-07:12"` | Backup window (UTC) |
| `maintenanceWindow` | string | `"wed:04:35-wed:05:05"` | Maintenance window (UTC) |
| `deletionProtection` | bool | `false` | Enable deletion protection |

## Generated Resources

The function creates the following AWS resources:

### Network Infrastructure
- **VPC**: `vectordb-vpc-{envSuffix}`
- **Internet Gateway**: `vectordb-igw-{envSuffix}`
- **Database Subnets**: `vectordb-subnet-{0,1,2}-{envSuffix}` (3 AZs)
- **Route Table**: `vectordb-route-table-{envSuffix}`
- **Security Group**: `vectordb-security-group-{envSuffix}`

### Database Infrastructure
- **Subnet Group**: `vectordb-subnet-group-{envSuffix}`
- **Aurora Cluster**: `vectordb-{claimName}`

### Connection Secrets

All resources write connection secrets to the claim's namespace:

- **VPC Secret**: `vectordb-vpc-{envSuffix}`
- **Subnet Secrets**: `vectordb-subnet-{0,1,2}-{envSuffix}`
- **Security Group Secret**: `vectordb-security-group-{envSuffix}`
- **Subnet Group Secret**: `vectordb-subnet-group-{envSuffix}`
- **Aurora Cluster Secret**: `vectordb-cluster-{envSuffix}`

The Aurora cluster secret contains:
- `vectordb_cluster_endpoints` - Writer endpoints
- `vectordb_cluster_reader_endpoints` - Read-only endpoints
- `vectordb_cluster_ids` - Cluster IDs
- `vectordb_master_passwords` - Master passwords
- `vpc_id` - VPC ID
- `database_subnet_group_name` - Subnet group name

## CIDR Allocation

The function automatically calculates subnet CIDR blocks:

- **VPC**: Configurable (default: `10.10.0.0/16`)
- **Database Subnets**: `/24` subnets starting at offset 6
  - Subnet 0: `10.10.6.0/24`
  - Subnet 1: `10.10.7.0/24`
  - Subnet 2: `10.10.8.0/24`

This leaves room for future public and private subnets (0-5).

## Development

### Prerequisites

- [Python 3.11][python]
- [Docker][docker]
- [Crossplane CLI][cli]

### Local Development

```shell
# Run the code in development mode
hatch run development

# Lint and format the code
hatch fmt

# Run unit tests
hatch test

# Build the function's runtime image
docker build . --tag=runtime

# Build a function package
crossplane xpkg build -f package --embed-runtime-image=runtime
```

### Testing

The function includes comprehensive tests:

- **Unit Tests**: Individual resource creation and configuration
- **Integration Tests**: Complete workflow validation
- **Configuration Tests**: Parameter validation and defaults
- **Error Handling**: Missing configuration scenarios

Run tests with:
```shell
hatch test
```

## Security Considerations

- **Public Access**: Database is publicly accessible on port 5432
- **Encryption**: Aurora storage encryption is enabled by default
- **Security Groups**: PostgreSQL port (5432) open from 0.0.0.0/0
- **Network Isolation**: Consider using private subnets with NAT for production

## Future Enhancements

- Support for private subnets with NAT Gateway
- VPC endpoints for AWS services
- Custom security group rules
- Multi-region deployment
- Backup and restore functionality

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run `hatch fmt` and `hatch test`
6. Submit a pull request

## License

Apache 2.0

[functions]: https://docs.crossplane.io/latest/concepts/composition-functions
[python]: https://python.org
[docker]: https://www.docker.com
[cli]: https://docs.crossplane.io/latest/cli
