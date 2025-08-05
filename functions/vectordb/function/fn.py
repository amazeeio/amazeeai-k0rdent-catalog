"""A Crossplane composition function for generating vector database infrastructure.

This function creates AWS infrastructure for a vector database with proper dependency management:
- Uses resource references (vpcIdRef, subnetIdRef, etc.) instead of label selectors for
  reliable dependencies
- Adds dependency annotations to ensure proper resource creation order
- Resources are created in the following order:
  1. VPC (no dependencies)
  2. Internet Gateway, Subnets, Route Table, Security Group (depend on VPC)
  3. Route Table Associations (depend on Subnets and Route Table)
  4. IGW Route (depends on IGW and Route Table)
  5. Security Group Rules (depend on Security Group)
  6. Subnet Group (depends on all Subnets)
  7. Aurora Cluster (depends on Subnet Group and Security Group)

Crossplane will automatically wait for dependencies to be ready before creating dependent resources.
"""

import dataclasses
import ipaddress
import json

import grpc
from crossplane.function import logging, resource, response
from crossplane.function.proto.v1 import run_function_pb2 as fnv1
from crossplane.function.proto.v1 import run_function_pb2_grpc as grpcv1


@dataclasses.dataclass
class VectorDBConfig:
    """Configuration for vector database infrastructure."""

    claim_name: str
    vpc_cidr: str
    region: str
    environment_suffix: str
    master_username: str
    postgres_cluster_name: str
    az_count: int = 3
    engine_version: str = "16.1"
    postgres_cluster_min_capacity: float = 0.5
    postgres_cluster_max_capacity: float = 16.0
    backup_retention_period: int = 7
    backup_window: str = "03:00-04:00"
    maintenance_window: str = "sun:04:00-sun:05:00"
    deletion_protection: bool = False
    namespace: str = "default"
    provider_config_ref: str = "default"
    instance_count: int = 2
    instance_class: str = "db.serverless"
    publicly_accessible: bool = True


class VectorDBFunctionRunner(grpcv1.FunctionRunnerService):
    """Generates AWS infrastructure for vector database."""

    def __init__(self):
        """Create a new VectorDBFunctionRunner."""
        self.log = logging.get_logger()

    async def RunFunction(
        self, req: fnv1.RunFunctionRequest, _: grpc.aio.ServicerContext
    ) -> fnv1.RunFunctionResponse:
        """Generate VPC, subnets, IGW, route tables, security groups, and Aurora cluster."""
        log = self.log.bind(tag=req.meta.tag)
        log.info("Running vector database function")

        response_obj = response.to(req)

        # Extract configuration from request
        config = self._extract_config(req)

        # Generate CIDR blocks for subnets
        subnet_cidrs = self._calculate_subnet_cidrs(config.vpc_cidr, config.az_count)

        # Create all resources with proper dependencies
        resources = []

        # 1. Create VPC (no dependencies)
        vpc_resource = self._create_vpc(config)
        resources.append(("vpc", vpc_resource))

        # 2. Create Internet Gateway (depends on VPC)
        igw_resource = self._create_internet_gateway(config)
        resources.append(("internet_gateway", igw_resource))

        # 3. Create database subnets (depend on VPC)
        subnet_resources = self._create_database_subnets(config, subnet_cidrs)
        for i, subnet in enumerate(subnet_resources):
            resources.append((f"subnet_{i}", subnet))

        # 4. Create route table for database subnets (depends on VPC)
        route_table_resource = self._create_database_route_table(config)
        resources.append(("route_table", route_table_resource))

        # 4.1. Create route to Internet Gateway (depends on IGW and route table)
        igw_route_resource = self._create_igw_route(config)
        resources.append(("igw_route", igw_route_resource))

        # 4.2. Create route table associations for each subnet (depend on subnets and route table)
        route_table_association_resources = self._create_route_table_associations(
            config, len(subnet_resources)
        )
        for i, association in enumerate(route_table_association_resources):
            resources.append((f"route_table_association_{i}", association))

        # 5. Create security group (depends on VPC)
        security_group_resource = self._create_database_security_group(config)
        resources.append(("security_group", security_group_resource))

        # 6. Create security group rule for PostgreSQL access (depends on security group)
        security_group_rule_resource = self._create_security_group_rule(config)
        resources.append(("security_group_rule", security_group_rule_resource))

        # 7. Create security group rule for all outbound traffic (depends on security group)
        egress_rule_resource = self._create_egress_rule(config)
        resources.append(("egress_rule", egress_rule_resource))

        # 8. Create subnet group (depends on subnets)
        subnet_group_resource = self._create_subnet_group(config)
        resources.append(("subnet_group", subnet_group_resource))

        # 9. Create monitoring role (no dependencies)
        monitoring_role_resource = self._create_monitoring_role(config)
        resources.append(("monitoring_role", monitoring_role_resource))

        # 10. Create Aurora cluster (depends on subnet group and security group)
        aurora_resource = self._create_aurora_cluster(config)
        resources.append(("aurora_cluster", aurora_resource))

        # 11. Create Aurora instances (depend on cluster, subnet group, security group,
        # and monitoring role)
        aurora_instance_resources = self._create_aurora_instances(config)
        for i, instance in enumerate(aurora_instance_resources):
            resources.append(
                (
                    f"aurora_instance_{i + 1}",
                    instance,
                )
            )

        # Add all resources to response
        for name, res in resources:
            resource.update(response_obj.desired.resources[name], res)

        return response_obj

    def _extract_config(self, req: fnv1.RunFunctionRequest) -> VectorDBConfig:
        """Extract configuration from request."""
        composite_data = resource.struct_to_dict(req.observed.composite.resource)
        spec_data = composite_data["spec"]

        # Extract namespace and name from the composite resource
        metadata = composite_data.get("metadata", {})
        namespace = metadata.get("namespace", "default")
        claim_name = metadata.get("name", "vectordb")

        return VectorDBConfig(
            claim_name=claim_name,
            vpc_cidr=spec_data.get("vpcCidr", "10.10.0.0/16"),
            region=spec_data.get("location", "us-west-2"),
            environment_suffix=spec_data.get("envSuffix", "dev"),
            master_username=spec_data.get("masterUsername", "postgres"),
            postgres_cluster_name=spec_data.get("clusterName", "vectordb-cluster"),
            az_count=int(spec_data.get("azCount", 3)),
            engine_version=spec_data.get("engineVersion", "16.1"),
            postgres_cluster_min_capacity=spec_data.get("minCapacity", 0.5),
            postgres_cluster_max_capacity=spec_data.get("maxCapacity", 16.0),
            backup_retention_period=int(spec_data.get("backupRetentionPeriod", 7)),
            backup_window=spec_data.get("backupWindow", "03:00-04:00"),
            maintenance_window=spec_data.get("maintenanceWindow", "sun:04:00-sun:05:00"),
            deletion_protection=spec_data.get("deletionProtection", False),
            namespace=namespace,
            provider_config_ref=spec_data.get("providerConfigRef", "default"),
            instance_count=int(spec_data.get("instanceCount", 2)),
            instance_class=spec_data.get("instanceClass", "db.serverless"),
            publicly_accessible=spec_data.get("publiclyAccessible", True),
        )

    def _calculate_subnet_cidrs(self, vpc_cidr: str, az_count: int) -> list[str]:
        """Calculate CIDR blocks for database subnets."""
        network = ipaddress.IPv4Network(vpc_cidr, strict=False)
        subnet_size = network.prefixlen + 8  # /24 subnets

        # Database subnets start at offset 6 (after public and private)
        database_subnets = []
        for i in range(az_count):
            subnet = network.subnets(new_prefix=subnet_size)
            for j, subnet_network in enumerate(subnet):
                if j == i + 6:  # Offset by 6 for database subnets
                    database_subnets.append(str(subnet_network))
                    break

        return database_subnets

    def _create_vpc(self, config: VectorDBConfig) -> dict:
        """Create VPC resource."""
        return {
            "apiVersion": "ec2.aws.upbound.io/v1beta1",
            "kind": "VPC",
            "spec": {
                "forProvider": {
                    "region": config.region,
                    "cidrBlock": config.vpc_cidr,
                    "enableDnsHostnames": True,
                    "enableDnsSupport": True,
                    "tags": {
                        "Name": f"{config.claim_name}-vpc-{config.environment_suffix}",
                        "App": config.claim_name,
                        "Environment": config.environment_suffix,
                    },
                },
                "providerConfigRef": {
                    "name": config.provider_config_ref,
                },
                "writeConnectionSecretToRef": {
                    "name": f"{config.claim_name}-vpc-{config.environment_suffix}",
                    "namespace": config.namespace,
                },
            },
            "metadata": {
                "name": f"{config.claim_name}-vpc-{config.environment_suffix}",
                "labels": {
                    "app": config.claim_name,
                    "environment": config.environment_suffix,
                },
            },
        }

    def _create_internet_gateway(self, config: VectorDBConfig) -> dict:
        """Create Internet Gateway and attach to VPC."""
        return {
            "apiVersion": "ec2.aws.upbound.io/v1beta1",
            "kind": "InternetGateway",
            "spec": {
                "forProvider": {
                    "region": config.region,
                    "vpcIdRef": {
                        "name": f"{config.claim_name}-vpc-{config.environment_suffix}",
                    },
                    "tags": {
                        "Name": f"{config.claim_name}-igw-{config.environment_suffix}",
                        "App": config.claim_name,
                        "Environment": config.environment_suffix,
                    },
                },
                "providerConfigRef": {
                    "name": config.provider_config_ref,
                },
                "writeConnectionSecretToRef": {
                    "name": f"{config.claim_name}-igw-{config.environment_suffix}",
                    "namespace": config.namespace,
                },
            },
            "metadata": {
                "name": f"{config.claim_name}-igw-{config.environment_suffix}",
                "labels": {
                    "app": config.claim_name,
                    "environment": config.environment_suffix,
                },
                "annotations": {
                    "crossplane.io/depends-on": "vpc",
                },
            },
        }

    def _create_database_subnets(self, config: VectorDBConfig, cidrs: list[str]) -> list[dict]:
        """Create database subnets in each AZ."""
        subnets = []
        availability_zones = [f"{config.region}a", f"{config.region}b", f"{config.region}c"]

        for i, (cidr, az) in enumerate(zip(cidrs, availability_zones, strict=False)):
            subnet = {
                "apiVersion": "ec2.aws.upbound.io/v1beta1",
                "kind": "Subnet",
                "spec": {
                    "forProvider": {
                        "region": config.region,
                        "vpcIdRef": {
                            "name": f"{config.claim_name}-vpc-{config.environment_suffix}",
                        },
                        "cidrBlock": cidr,
                        "availabilityZone": az,
                        "mapPublicIpOnLaunch": True,
                        "tags": {
                            "Name": f"{config.claim_name}-subnet-{i}-{config.environment_suffix}",
                            "App": config.claim_name,
                            "Environment": config.environment_suffix,
                            "Type": "database",
                        },
                    },
                    "providerConfigRef": {
                        "name": config.provider_config_ref,
                    },
                    "writeConnectionSecretToRef": {
                        "name": f"{config.claim_name}-subnet-{i}-{config.environment_suffix}",
                        "namespace": config.namespace,
                    },
                },
                "metadata": {
                    "name": f"{config.claim_name}-subnet-{i}-{config.environment_suffix}",
                    "labels": {
                        "app": config.claim_name,
                        "environment": config.environment_suffix,
                        "type": "database",
                    },
                    "annotations": {
                        "crossplane.io/depends-on": "vpc",
                    },
                },
            }
            subnets.append(subnet)

        return subnets

    def _create_route_table_associations(
        self, config: VectorDBConfig, subnet_count: int
    ) -> list[dict]:
        """Create route table associations for each subnet."""
        associations = []

        for i in range(subnet_count):
            association = {
                "apiVersion": "ec2.aws.upbound.io/v1beta1",
                "kind": "RouteTableAssociation",
                "spec": {
                    "forProvider": {
                        "region": config.region,
                        "subnetIdRef": {
                            "name": f"{config.claim_name}-subnet-{i}-{config.environment_suffix}",
                        },
                        "routeTableIdRef": {
                            "name": f"{config.claim_name}-route-table-{config.environment_suffix}",
                        },
                    },
                    "providerConfigRef": {
                        "name": config.provider_config_ref,
                    },
                    "writeConnectionSecretToRef": {
                        "name": (
                            f"{config.claim_name}-route-table-association-"
                            f"{i}-{config.environment_suffix}"
                        ),
                        "namespace": config.namespace,
                    },
                },
                "metadata": {
                    "name": (
                        f"{config.claim_name}-route-table-association-"
                        f"{i}-{config.environment_suffix}"
                    ),
                    "labels": {
                        "app": config.claim_name,
                        "environment": config.environment_suffix,
                        "type": "database",
                    },
                    "annotations": {
                        "crossplane.io/depends-on": f"subnet_{i},route_table",
                    },
                },
            }
            associations.append(association)

        return associations

    def _create_igw_route(self, config: VectorDBConfig) -> dict:
        """Create route to Internet Gateway."""
        return {
            "apiVersion": "ec2.aws.upbound.io/v1beta1",
            "kind": "Route",
            "spec": {
                "forProvider": {
                    "region": config.region,
                    "destinationCidrBlock": "0.0.0.0/0",
                    "gatewayIdRef": {
                        "name": f"{config.claim_name}-igw-{config.environment_suffix}",
                    },
                    "routeTableIdRef": {
                        "name": f"{config.claim_name}-route-table-{config.environment_suffix}",
                    },
                },
                "providerConfigRef": {
                    "name": config.provider_config_ref,
                },
                "writeConnectionSecretToRef": {
                    "name": f"{config.claim_name}-igw-route-{config.environment_suffix}",
                    "namespace": config.namespace,
                },
            },
            "metadata": {
                "name": f"{config.claim_name}-igw-route-{config.environment_suffix}",
                "labels": {
                    "app": config.claim_name,
                    "environment": config.environment_suffix,
                    "type": "database",
                },
                "annotations": {
                    "crossplane.io/depends-on": "internet_gateway,route_table",
                },
            },
        }

    def _create_database_route_table(self, config: VectorDBConfig) -> dict:
        """Create route table with IGW route for database subnets."""
        return {
            "apiVersion": "ec2.aws.upbound.io/v1beta1",
            "kind": "RouteTable",
            "spec": {
                "forProvider": {
                    "region": config.region,
                    "vpcIdRef": {
                        "name": f"{config.claim_name}-vpc-{config.environment_suffix}",
                    },
                    "tags": {
                        "Name": f"{config.claim_name}-route-table-{config.environment_suffix}",
                        "App": config.claim_name,
                        "Environment": config.environment_suffix,
                        "Type": "database",
                    },
                },
                "providerConfigRef": {
                    "name": config.provider_config_ref,
                },
                "writeConnectionSecretToRef": {
                    "name": f"{config.claim_name}-route-table-{config.environment_suffix}",
                    "namespace": config.namespace,
                },
            },
            "metadata": {
                "name": f"{config.claim_name}-route-table-{config.environment_suffix}",
                "labels": {
                    "app": config.claim_name,
                    "environment": config.environment_suffix,
                    "type": "database",
                },
                "annotations": {
                    "crossplane.io/depends-on": "vpc",
                },
            },
        }

    def _create_database_security_group(self, config: VectorDBConfig) -> dict:
        """Create security group allowing PostgreSQL access."""
        return {
            "apiVersion": "ec2.aws.upbound.io/v1beta1",
            "kind": "SecurityGroup",
            "spec": {
                "forProvider": {
                    "region": config.region,
                    "vpcIdRef": {
                        "name": f"{config.claim_name}-vpc-{config.environment_suffix}",
                    },
                    "tags": {
                        "Name": f"{config.claim_name}-security-group-{config.environment_suffix}",
                        "App": config.claim_name,
                        "Environment": config.environment_suffix,
                    },
                },
                "providerConfigRef": {
                    "name": config.provider_config_ref,
                },
                "writeConnectionSecretToRef": {
                    "name": f"{config.claim_name}-security-group-{config.environment_suffix}",
                    "namespace": config.namespace,
                },
            },
            "metadata": {
                "name": f"{config.claim_name}-security-group-{config.environment_suffix}",
                "labels": {
                    "app": config.claim_name,
                    "environment": config.environment_suffix,
                },
                "annotations": {
                    "crossplane.io/depends-on": "vpc",
                },
            },
        }

    def _create_security_group_rule(self, config: VectorDBConfig) -> dict:
        """Create security group rule allowing PostgreSQL access."""
        return {
            "apiVersion": "ec2.aws.upbound.io/v1beta1",
            "kind": "SecurityGroupRule",
            "spec": {
                "forProvider": {
                    "region": config.region,
                    "type": "ingress",
                    "fromPort": 5432,
                    "toPort": 5432,
                    "protocol": "tcp",
                    "cidrBlocks": ["0.0.0.0/0"],
                    "description": "PostgreSQL access",
                    "securityGroupIdRef": {
                        "name": f"{config.claim_name}-security-group-{config.environment_suffix}",
                    },
                },
                "providerConfigRef": {
                    "name": config.provider_config_ref,
                },
            },
            "metadata": {
                "name": f"{config.claim_name}-postgres-ingress-{config.environment_suffix}",
                "labels": {
                    "app": config.claim_name,
                    "environment": config.environment_suffix,
                },
                "annotations": {
                    "crossplane.io/depends-on": "security_group",
                },
            },
        }

    def _create_egress_rule(self, config: VectorDBConfig) -> dict:
        """Create security group rule allowing all outbound traffic."""
        return {
            "apiVersion": "ec2.aws.upbound.io/v1beta1",
            "kind": "SecurityGroupRule",
            "spec": {
                "forProvider": {
                    "region": config.region,
                    "type": "egress",
                    "fromPort": 0,
                    "toPort": 0,
                    "protocol": "-1",  # All protocols
                    "cidrBlocks": ["0.0.0.0/0"],
                    "description": "Allow all outbound traffic",
                    "securityGroupIdRef": {
                        "name": f"{config.claim_name}-security-group-{config.environment_suffix}",
                    },
                },
                "providerConfigRef": {
                    "name": config.provider_config_ref,
                },
            },
            "metadata": {
                "name": f"{config.claim_name}-egress-all-{config.environment_suffix}",
                "labels": {
                    "app": config.claim_name,
                    "environment": config.environment_suffix,
                },
                "annotations": {
                    "crossplane.io/depends-on": "security_group",
                },
            },
        }

    def _create_subnet_group(self, config: VectorDBConfig) -> dict:
        """Create RDS subnet group from subnet IDs."""
        return {
            "apiVersion": "rds.aws.upbound.io/v1beta1",
            "kind": "SubnetGroup",
            "spec": {
                "forProvider": {
                    "region": config.region,
                    "subnetIdRefs": [
                        {"name": f"{config.claim_name}-subnet-{i}-{config.environment_suffix}"}
                        for i in range(config.az_count)
                    ],
                    "description": f"Subnet group for {config.postgres_cluster_name}",
                    "tags": {
                        "Name": f"{config.claim_name}-subnet-group-{config.environment_suffix}",
                        "App": config.claim_name,
                        "Environment": config.environment_suffix,
                    },
                },
                "providerConfigRef": {
                    "name": config.provider_config_ref,
                },
                "writeConnectionSecretToRef": {
                    "name": f"{config.claim_name}-subnet-group-{config.environment_suffix}",
                    "namespace": config.namespace,
                },
            },
            "metadata": {
                "name": f"{config.claim_name}-subnet-group-{config.environment_suffix}",
                "labels": {
                    "app": config.claim_name,
                    "environment": config.environment_suffix,
                },
                "annotations": {
                    "crossplane.io/depends-on": ",".join(
                        [f"subnet_{i}" for i in range(config.az_count)]
                    ),
                },
            },
        }

    def _create_aurora_cluster(self, config: VectorDBConfig) -> dict:
        """Create Aurora PostgreSQL cluster."""
        return {
            "apiVersion": "rds.aws.upbound.io/v1beta1",
            "kind": "Cluster",
            "spec": {
                "forProvider": {
                    "region": config.region,
                    "engine": "aurora-postgresql",
                    "engineVersion": config.engine_version,
                    "engineMode": "provisioned",
                    "storageEncrypted": True,
                    "masterUsername": config.master_username,
                    "autoGeneratePassword": True,
                    "masterPasswordSecretRef": {
                        "name": f"{config.claim_name}-password-{config.environment_suffix}",
                        "namespace": config.namespace,
                        "key": "password",
                    },
                    "dbSubnetGroupNameRef": {
                        "name": f"{config.claim_name}-subnet-group-{config.environment_suffix}",
                    },
                    "vpcSecurityGroupIdRefs": [
                        {"name": f"{config.claim_name}-security-group-{config.environment_suffix}"}
                    ],
                    "backupRetentionPeriod": config.backup_retention_period,
                    "preferredBackupWindow": config.backup_window,
                    "preferredMaintenanceWindow": config.maintenance_window,
                    "serverlessv2ScalingConfiguration": [
                        {
                            "minCapacity": config.postgres_cluster_min_capacity,
                            "maxCapacity": config.postgres_cluster_max_capacity,
                        },
                    ],
                    "deletionProtection": config.deletion_protection,
                    "skipFinalSnapshot": False,
                    "finalSnapshotIdentifier": (
                        f"{config.claim_name}-final-snapshot-{config.environment_suffix}"
                    ),
                    "copyTagsToSnapshot": True,
                    "iamDatabaseAuthenticationEnabled": False,
                    "enableHttpEndpoint": False,
                    "performanceInsightsEnabled": True,
                    "performanceInsightsRetentionPeriod": 7,
                    "dbClusterParameterGroupName": "default.aurora-postgresql16",
                    "tags": {
                        "Name": f"{config.claim_name}-cluster-{config.environment_suffix}",
                        "App": config.claim_name,
                        "Environment": config.environment_suffix,
                    },
                },
                "providerConfigRef": {
                    "name": config.provider_config_ref,
                },
                "writeConnectionSecretToRef": {
                    "name": f"{config.claim_name}-cluster-{config.environment_suffix}",
                    "namespace": config.namespace,
                },
            },
            "metadata": {
                "name": config.postgres_cluster_name,
                "labels": {
                    "app": config.claim_name,
                    "environment": config.environment_suffix,
                },
                "annotations": {
                    "crossplane.io/depends-on": "subnet_group,security_group,password_secret",
                },
            },
        }

    def _create_aurora_instances(self, config: VectorDBConfig) -> list[dict]:
        """Create Aurora PostgreSQL cluster instances."""
        instances = []
        for i in range(config.instance_count):
            instance_name = f"{config.postgres_cluster_name}-instance-{i + 1}"
            instance = {
                "apiVersion": "rds.aws.upbound.io/v1beta1",
                "kind": "ClusterInstance",
                "spec": {
                    "forProvider": {
                        "region": config.region,
                        "engine": "aurora-postgresql",
                        "engineVersion": config.engine_version,
                        "instanceClass": config.instance_class,
                        "publiclyAccessible": config.publicly_accessible,
                        "clusterIdentifierRef": {
                            "name": config.postgres_cluster_name,
                        },
                        "dbSubnetGroupNameRef": {
                            "name": f"{config.claim_name}-subnet-group-{config.environment_suffix}",
                        },
                        "performanceInsightsEnabled": True,
                        "performanceInsightsRetentionPeriod": 7,
                        "dbParameterGroupName": "default.aurora-postgresql16",
                        "autoMinorVersionUpgrade": True,
                        "monitoringInterval": 60,
                        "monitoringRoleArnRef": {
                            "name": (
                                f"{config.claim_name}-monitoring-role-{config.environment_suffix}"
                            ),
                        },
                        "promotionTier": i,
                        "tags": {
                            "Name": (
                                f"{config.claim_name}-instance-{i + 1}-{config.environment_suffix}"
                            ),
                            "App": config.claim_name,
                            "Environment": config.environment_suffix,
                        },
                    },
                    "providerConfigRef": {
                        "name": config.provider_config_ref,
                    },
                    "writeConnectionSecretToRef": {
                        "name": f"{config.claim_name}-instance-{i + 1}-{config.environment_suffix}",
                        "namespace": config.namespace,
                    },
                },
                "metadata": {
                    "name": instance_name,
                    "labels": {
                        "app": config.claim_name,
                        "environment": config.environment_suffix,
                    },
                    "annotations": {
                        "crossplane.io/depends-on": (
                            "aurora_cluster,subnet_group,security_group,monitoring_role"
                        ),
                    },
                },
            }
            instances.append(instance)
        return instances

    def _create_monitoring_role(self, config: VectorDBConfig) -> dict:
        """Create IAM role for RDS enhanced monitoring."""
        return {
            "apiVersion": "iam.aws.upbound.io/v1beta1",
            "kind": "Role",
            "spec": {
                "forProvider": {
                    "assumeRolePolicy": json.dumps(
                        {
                            "Version": "2012-10-17",
                            "Statement": [
                                {
                                    "Sid": "",
                                    "Effect": "Allow",
                                    "Principal": {"Service": "monitoring.rds.amazonaws.com"},
                                    "Action": "sts:AssumeRole",
                                }
                            ],
                        }
                    ),
                    "description": f"Role for RDS enhanced monitoring for {config.claim_name}",
                    "managedPolicyArns": [
                        "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
                    ],
                    "tags": {
                        "Name": f"{config.claim_name}-monitoring-role-{config.environment_suffix}",
                        "App": config.claim_name,
                        "Environment": config.environment_suffix,
                    },
                },
                "providerConfigRef": {
                    "name": config.provider_config_ref,
                },
            },
            "metadata": {
                "name": f"{config.claim_name}-monitoring-role-{config.environment_suffix}",
                "labels": {
                    "app": config.claim_name,
                    "environment": config.environment_suffix,
                },
            },
        }


# Keep the original FunctionRunner for backward compatibility
class FunctionRunner(VectorDBFunctionRunner):
    """Backward compatibility wrapper."""
