# function-vectordb

[![CI](https://github.com/crossplane/function-template-python/actions/workflows/ci.yml/badge.svg)](https://github.com/crossplane/function-template-go/actions/workflows/ci.yml)

A Crossplane composition function for creating AWS Aurora PostgreSQL infrastructure optimized for vector database workloads.

## What it does

This function creates a complete AWS infrastructure stack for running vector databases on Aurora PostgreSQL, including:

- **Networking**: VPC with public, private, and database subnets across 2 availability zones
- **Database**: Aurora PostgreSQL Serverless v2 cluster with vector extension support
- **Security**: Security groups, IAM roles, and parameter groups configured for vector operations
- **Monitoring**: Enhanced monitoring and Performance Insights enabled
- **Backup**: Automated backups with configurable retention and maintenance windows

## Configuration

The function accepts the following configuration parameters in the composite resource spec:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `location` | **required** | AWS region (e.g., `us-east-1`, `eu-central-1`) |
| `engineVersion` | `16.6` | Aurora PostgreSQL engine version |
| `minCapacity` | `2` | Minimum ACU for Serverless v2 |
| `maxCapacity` | `16` | Maximum ACU for Serverless v2 |
| `databaseName` | `vectordb` | Name of the database |
| `masterUsername` | `postgres` | Master database username |
| `backupRetentionPeriod` | `7` | Days to retain backups |
| `backupWindow` | `06:42-07:12` | Daily backup window |
| `maintenanceWindow` | `wed:04:35-wed:05:05` | Weekly maintenance window |
| `deletionProtection` | `true` | Enable deletion protection |
| `generatePassword` | `true` | Generate random master password |

## Testing and Verification

### Prerequisites

- Python 3.8+
- Crossplane CLI
- Docker

### Development Mode

Run the function in development mode for testing:

```shell
# Start the function in development mode
hatch run development
```

### Manual Testing with Crossplane CLI

Test the function directly with the Crossplane CLI:

```shell
# Build the function package
crossplane xpkg build -f package --embed-runtime-image=runtime

# Test rendering with the example XR
crossplane render example/xr.yaml example/composition.yaml example/functions.yaml

## Development

### Code Quality

```shell
# Format and lint code
hatch fmt

# Run type checking
hatch run typecheck
```

### Building

```shell
# Build the runtime image
docker build . --tag=runtime

# Build the function package
crossplane xpkg build -f package --embed-runtime-image=runtime
```

### Test with Example Configuration

1. **Apply the function configuration**:
   ```shell
   kubectl apply -f example/functions.yaml
   ```

2. **Apply the composition**:
   ```shell
   kubectl apply -f example/composition.yaml
   ```

3. **Test with the example XR**:
   ```shell
   # Apply the example composite resource
   kubectl apply -f example/xr.yaml

   # Or test with custom configuration
   cat <<EOF | kubectl apply -f -
   apiVersion: example.crossplane.io/v1
   kind: XR
   metadata:
     name: my-vector-db
   spec:
     location: us-east-1
     engineVersion: "16.7"
     minCapacity: 4
     maxCapacity: 32
     databaseName: myvectordb
     masterUsername: admin
     backupRetentionPeriod: 14
     deletionProtection: false
   EOF
   ```

4. **Verify the resources**:
   ```shell
   # Check the composite resource status
   kubectl get xr

   # Check created resources
   kubectl get vpc,subnet,securitygroup,cluster,instance
   ```

### Unit Tests

Run the comprehensive test suite:

```shell
# Run all tests
hatch test

# Run with verbose output
hatch test -v
```

The tests verify:
- Basic infrastructure creation with default values
- Custom configuration handling
- Availability zone mapping for different regions
- Resource structure and metadata
- Parameter validation


## Architecture

The function creates 25 AWS resources:

1. **VPC** - Main network with DNS support
2. **Internet Gateway** - Internet connectivity
3. **Subnets** - 6 subnets (2 public, 2 private, 2 database) across 2 AZs
4. **Route Tables** - 2 route tables for public and database traffic
5. **Routes** - Internet gateway routes
6. **Route Table Associations** - 4 associations linking subnets to route tables
7. **Security Group** - Aurora PostgreSQL access (port 5432)
8. **IAM Role** - Enhanced monitoring role
9. **Parameter Groups** - 2 parameter groups with vector extension
10. **Random Password** - Generated master password (optional)
11. **Aurora Cluster** - PostgreSQL cluster with vector support
12. **Aurora Instance** - Serverless v2 instance
13. **Secret** - Kubernetes secret with connection details

## Supported Regions

The function includes availability zone mapping for:
- `eu-central-2`, `eu-west-2`, `eu-central-1`
- `us-east-1`, `us-east-2`
- `ap-southeast-2`, `ca-central-1`, `af-south-1`

## Learn More

- [Crossplane Composition Functions][functions]
- [Writing Composition Functions in Python][function guide]
- [Function SDK Python Documentation][package docs]

[functions]: https://docs.crossplane.io/latest/concepts/composition-functions
[function guide]: https://docs.crossplane.io/knowledge-base/guides/write-a-composition-function-in-python
[package docs]: https://crossplane.github.io/function-sdk-python
