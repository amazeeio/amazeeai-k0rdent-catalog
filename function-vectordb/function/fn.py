"""A Crossplane composition function for creating vector database infrastructure."""

import grpc
from crossplane.function import logging, resource, response
from crossplane.function.proto.v1 import run_function_pb2 as fnv1
from crossplane.function.proto.v1 import run_function_pb2_grpc as grpcv1
from google.protobuf import json_format


class FunctionRunner(grpcv1.FunctionRunnerService):
    """A FunctionRunner handles gRPC RunFunctionRequests."""

    def __init__(self):
        """Create a new FunctionRunner."""
        self.log = logging.get_logger()

    def _get_availability_zone(self, region: str, az_suffix: str) -> str:
        """Get availability zone for a given region and suffix."""
        az_mapping = {
            "eu-central-2": f"eu-central-2{az_suffix}",
            "eu-west-2": f"eu-west-2{az_suffix}",
            "eu-central-1": f"eu-central-1{az_suffix}",
            "us-east-1": f"us-east-1{az_suffix}",
            "us-east-2": f"us-east-2{az_suffix}",
            "ap-southeast-2": f"ap-southeast-2{az_suffix}",
            "ca-central-1": f"ca-central-1{az_suffix}",
            "af-south-1": f"af-south-1{az_suffix}",
        }
        return az_mapping.get(region, f"{region}{az_suffix}")

    async def RunFunction(
        self, req: fnv1.RunFunctionRequest, _: grpc.aio.ServicerContext
    ) -> fnv1.RunFunctionResponse:
        """Run the function to create vector database infrastructure."""
        log = self.log.bind(tag=req.meta.tag)
        log.info("Running vector database function")

        rsp = response.to(req)

        # Extract configuration from the composite resource
        # Convert protobuf Struct to dictionary for easier access
        spec_dict = json_format.MessageToDict(req.observed.composite.resource["spec"])
        location = spec_dict["location"]
        engine_version = spec_dict.get("engineVersion", "16.6")
        min_capacity = spec_dict.get("minCapacity", 2)
        max_capacity = spec_dict.get("maxCapacity", 16)
        database_name = spec_dict.get("databaseName", "vectordb")
        master_username = spec_dict.get("masterUsername", "postgres")
        backup_retention_period = spec_dict.get("backupRetentionPeriod", 7)
        backup_window = spec_dict.get("backupWindow", "06:42-07:12")
        maintenance_window = spec_dict.get("maintenanceWindow", "wed:04:35-wed:05:05")
        deletion_protection = spec_dict.get("deletionProtection", True)
        generate_password = spec_dict.get("generatePassword", True)

        log.info(
            "Creating vector database infrastructure",
            location=location,
            engine_version=engine_version,
        )

        # 1. VPC
        resource.update(
            rsp.desired.resources["vpc"],
            {
                "apiVersion": "vpc.aws.upbound.io/v1beta1",
                "kind": "VPC",
                "metadata": {
                    "annotations": {
                        "crossplane.io/external-name": "vector-db-vpc",
                    },
                },
                "spec": {
                    "forProvider": {
                        "region": location,
                        "cidrBlock": "10.0.0.0/16",
                        "enableDnsHostnames": True,
                        "enableDnsSupport": True,
                        "tags": {
                            "Name": "vector-db-vpc",
                        },
                    },
                    "providerConfigRef": {
                        "name": "creds-provider",
                    },
                },
            },
        )

        # 2. Internet Gateway
        resource.update(
            rsp.desired.resources["internet-gateway"],
            {
                "apiVersion": "vpc.aws.upbound.io/v1beta1",
                "kind": "InternetGateway",
                "metadata": {
                    "annotations": {
                        "crossplane.io/external-name": "vector-db-igw",
                    },
                },
                "spec": {
                    "forProvider": {
                        "region": location,
                        "vpcIdSelector": {
                            "matchControllerRef": True,
                        },
                        "tags": {
                            "Name": "vector-db-igw",
                        },
                    },
                    "providerConfigRef": {
                        "name": "creds-provider",
                    },
                },
            },
        )

        # 3. Public Subnets
        for i, az_suffix in enumerate(["a", "b"]):
            resource.update(
                rsp.desired.resources[f"public-subnet-{i + 1}"],
                {
                    "apiVersion": "vpc.aws.upbound.io/v1beta1",
                    "kind": "Subnet",
                    "metadata": {
                        "annotations": {
                            "crossplane.io/external-name": (
                                f"vector-db-public-subnet-{i + 1}"
                            ),
                        },
                    },
                    "spec": {
                        "forProvider": {
                            "region": location,
                            "vpcIdSelector": {
                                "matchControllerRef": True,
                            },
                            "cidrBlock": f"10.0.{i + 1}.0/24",
                            "availabilityZone": (
                                self._get_availability_zone(location, az_suffix)
                            ),
                            "mapPublicIpOnLaunch": True,
                            "tags": {
                                "Name": f"vector-db-public-subnet-{i + 1}",
                            },
                        },
                        "providerConfigRef": {
                            "name": "creds-provider",
                        },
                    },
                },
            )

        # 4. Private Subnets
        for i, az_suffix in enumerate(["a", "b"]):
            resource.update(
                rsp.desired.resources[f"private-subnet-{i + 1}"],
                {
                    "apiVersion": "vpc.aws.upbound.io/v1beta1",
                    "kind": "Subnet",
                    "metadata": {
                        "annotations": {
                            "crossplane.io/external-name": (
                                f"vector-db-private-subnet-{i + 1}"
                            ),
                        },
                    },
                    "spec": {
                        "forProvider": {
                            "region": location,
                            "vpcIdSelector": {
                                "matchControllerRef": True,
                            },
                            "cidrBlock": f"10.0.{i + 3}.0/24",
                            "availabilityZone": (
                                self._get_availability_zone(location, az_suffix)
                            ),
                            "tags": {
                                "Name": f"vector-db-private-subnet-{i + 1}",
                            },
                        },
                        "providerConfigRef": {
                            "name": "creds-provider",
                        },
                    },
                },
            )

        # 5. Database Subnets
        for i, az_suffix in enumerate(["a", "b"]):
            resource.update(
                rsp.desired.resources[f"database-subnet-{i + 1}"],
                {
                    "apiVersion": "vpc.aws.upbound.io/v1beta1",
                    "kind": "Subnet",
                    "metadata": {
                        "annotations": {
                            "crossplane.io/external-name": (
                                f"vector-db-database-subnet-{i + 1}"
                            ),
                        },
                    },
                    "spec": {
                        "forProvider": {
                            "region": location,
                            "vpcIdSelector": {
                                "matchControllerRef": True,
                            },
                            "cidrBlock": f"10.0.{i + 5}.0/24",
                            "availabilityZone": (
                                self._get_availability_zone(location, az_suffix)
                            ),
                            "tags": {
                                "Name": f"vector-db-database-subnet-{i + 1}",
                            },
                        },
                        "providerConfigRef": {
                            "name": "creds-provider",
                        },
                    },
                },
            )

        # 6. Database Subnet Group
        resource.update(
            rsp.desired.resources["database-subnet-group"],
            {
                "apiVersion": "rds.aws.upbound.io/v1beta1",
                "kind": "SubnetGroup",
                "metadata": {
                    "annotations": {
                        "crossplane.io/external-name": "vector-db-subnet-group",
                    },
                },
                "spec": {
                    "forProvider": {
                        "region": location,
                        "subnetIds": [
                            "dummy-subnet-1",
                            "dummy-subnet-2",
                        ],
                        "tags": {
                            "Name": "vector-db-subnet-group",
                        },
                    },
                    "providerConfigRef": {
                        "name": "creds-provider",
                    },
                },
            },
        )

        # 7. Route Tables
        resource.update(
            rsp.desired.resources["public-route-table"],
            {
                "apiVersion": "vpc.aws.upbound.io/v1beta1",
                "kind": "RouteTable",
                "metadata": {
                    "annotations": {
                        "crossplane.io/external-name": "vector-db-public-rt",
                    },
                },
                "spec": {
                    "forProvider": {
                        "region": location,
                        "vpcIdSelector": {
                            "matchControllerRef": True,
                        },
                        "tags": {
                            "Name": "vector-db-public-rt",
                        },
                    },
                    "providerConfigRef": {
                        "name": "creds-provider",
                    },
                },
            },
        )

        resource.update(
            rsp.desired.resources["database-route-table"],
            {
                "apiVersion": "vpc.aws.upbound.io/v1beta1",
                "kind": "RouteTable",
                "metadata": {
                    "annotations": {
                        "crossplane.io/external-name": "vector-db-database-rt",
                    },
                },
                "spec": {
                    "forProvider": {
                        "region": location,
                        "vpcIdSelector": {
                            "matchControllerRef": True,
                        },
                        "tags": {
                            "Name": "vector-db-database-rt",
                        },
                    },
                    "providerConfigRef": {
                        "name": "creds-provider",
                    },
                },
            },
        )

        # 8. Routes
        resource.update(
            rsp.desired.resources["public-route"],
            {
                "apiVersion": "vpc.aws.upbound.io/v1beta1",
                "kind": "Route",
                "metadata": {
                    "annotations": {
                        "crossplane.io/external-name": "vector-db-public-route",
                    },
                },
                "spec": {
                    "forProvider": {
                        "region": location,
                        "routeTableIdSelector": {
                            "matchControllerRef": True,
                        },
                        "destinationCidrBlock": "0.0.0.0/0",
                        "gatewayIdSelector": {
                            "matchControllerRef": True,
                        },
                    },
                    "providerConfigRef": {
                        "name": "creds-provider",
                    },
                },
            },
        )

        resource.update(
            rsp.desired.resources["database-route"],
            {
                "apiVersion": "vpc.aws.upbound.io/v1beta1",
                "kind": "Route",
                "metadata": {
                    "annotations": {
                        "crossplane.io/external-name": "vector-db-database-route",
                    },
                },
                "spec": {
                    "forProvider": {
                        "region": location,
                        "routeTableIdSelector": {
                            "matchControllerRef": True,
                        },
                        "destinationCidrBlock": "0.0.0.0/0",
                        "gatewayIdSelector": {
                            "matchControllerRef": True,
                        },
                    },
                    "providerConfigRef": {
                        "name": "creds-provider",
                    },
                },
            },
        )

        # 9. Route Table Associations
        for i in range(1, 3):
            resource.update(
                rsp.desired.resources[f"public-rt-assoc-{i}"],
                {
                    "apiVersion": "vpc.aws.upbound.io/v1beta1",
                    "kind": "RouteTableAssociation",
                    "metadata": {
                        "annotations": {
                            "crossplane.io/external-name": (
                                f"vector-db-public-rt-assoc-{i}"
                            ),
                        },
                    },
                    "spec": {
                        "forProvider": {
                            "region": location,
                            "subnetIdSelector": {
                                "matchControllerRef": True,
                            },
                            "routeTableIdSelector": {
                                "matchControllerRef": True,
                            },
                        },
                        "providerConfigRef": {
                            "name": "creds-provider",
                        },
                    },
                },
            )

        for i in range(1, 3):
            resource.update(
                rsp.desired.resources[f"database-rt-assoc-{i}"],
                {
                    "apiVersion": "vpc.aws.upbound.io/v1beta1",
                    "kind": "RouteTableAssociation",
                    "metadata": {
                        "annotations": {
                            "crossplane.io/external-name": (
                                f"vector-db-database-rt-assoc-{i}"
                            ),
                        },
                    },
                    "spec": {
                        "forProvider": {
                            "region": location,
                            "subnetIdSelector": {
                                "matchControllerRef": True,
                            },
                            "routeTableIdSelector": {
                                "matchControllerRef": True,
                            },
                        },
                        "providerConfigRef": {
                            "name": "creds-provider",
                        },
                    },
                },
            )

        # 10. Security Group for Aurora
        resource.update(
            rsp.desired.resources["aurora-security-group"],
            {
                "apiVersion": "vpc.aws.upbound.io/v1beta1",
                "kind": "SecurityGroup",
                "metadata": {
                    "annotations": {
                        "crossplane.io/external-name": "vector-db-aurora-sg",
                    },
                },
                "spec": {
                    "forProvider": {
                        "region": location,
                        "vpcIdSelector": {
                            "matchControllerRef": True,
                        },
                        "description": "Security group for Aurora PostgreSQL cluster",
                        "ingress": [
                            {
                                "description": "PostgreSQL access",
                                "fromPort": 5432,
                                "toPort": 5432,
                                "protocol": "tcp",
                                "cidrBlocks": ["0.0.0.0/0"],
                            },
                        ],
                        "egress": [
                            {
                                "description": "All outbound traffic",
                                "fromPort": 0,
                                "toPort": 0,
                                "protocol": "-1",
                                "cidrBlocks": ["0.0.0.0/0"],
                            },
                        ],
                        "tags": {
                            "Name": "vector-db-aurora-sg",
                        },
                    },
                    "providerConfigRef": {
                        "name": "creds-provider",
                    },
                },
            },
        )

        # 11. IAM Role for RDS Monitoring
        resource.update(
            rsp.desired.resources["rds-monitoring-role"],
            {
                "apiVersion": "iam.aws.upbound.io/v1beta1",
                "kind": "Role",
                "metadata": {
                    "annotations": {
                        "crossplane.io/external-name": "vector-db-monitoring-role",
                    },
                },
                "spec": {
                    "forProvider": {
                        "region": location,
                        "assumeRolePolicy": """{
                            "Version": "2012-10-17",
                            "Statement": [
                                {
                                    "Effect": "Allow",
                                    "Principal": {
                                        "Service": "monitoring.rds.amazonaws.com"
                                    },
                                    "Action": "sts:AssumeRole"
                                }
                            ]
                        }""",
                        "managedPolicyArns": [
                            "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole",
                        ],
                        "tags": {
                            "Name": "vector-db-monitoring-role",
                        },
                    },
                    "providerConfigRef": {
                        "name": "creds-provider",
                    },
                },
            },
        )

        # 12. Parameter Group for vector extension
        resource.update(
            rsp.desired.resources["parameter-group"],
            {
                "apiVersion": "rds.aws.upbound.io/v1beta1",
                "kind": "ParameterGroup",
                "metadata": {
                    "annotations": {
                        "crossplane.io/external-name": "vector-db-parameter-group",
                    },
                },
                "spec": {
                    "forProvider": {
                        "region": location,
                        "family": "aurora-postgresql16",
                        "description": "Parameter group for vector extension",
                        "parameter": [
                            {
                                "name": "shared_preload_libraries",
                                "value": "vector",
                            },
                        ],
                        "tags": {
                            "Name": "vector-db-parameter-group",
                        },
                    },
                    "providerConfigRef": {
                        "name": "creds-provider",
                    },
                },
            },
        )

        # 13. Cluster Parameter Group for vector extension
        resource.update(
            rsp.desired.resources["cluster-parameter-group"],
            {
                "apiVersion": "rds.aws.upbound.io/v1beta1",
                "kind": "ClusterParameterGroup",
                "metadata": {
                    "annotations": {
                        "crossplane.io/external-name": (
                            "vector-db-cluster-parameter-group"
                        ),
                    },
                },
                "spec": {
                    "forProvider": {
                        "region": location,
                        "family": "aurora-postgresql16",
                        "description": "Cluster parameter group for vector extension",
                        "parameter": [
                            {
                                "name": "shared_preload_libraries",
                                "value": "vector",
                            },
                        ],
                        "tags": {
                            "Name": "vector-db-cluster-parameter-group",
                        },
                    },
                    "providerConfigRef": {
                        "name": "creds-provider",
                    },
                },
            },
        )

        # 14. Random password generator
        if generate_password:
            resource.update(
                rsp.desired.resources["random-password"],
                {
                    "apiVersion": "random.upbound.io/v1beta1",
                    "kind": "Password",
                    "metadata": {
                        "annotations": {
                            "crossplane.io/external-name": "vector-db-password",
                        },
                    },
                    "spec": {
                        "forProvider": {
                            "length": 16,
                            "special": True,
                            "overrideSpecial": "!#$%&*()-_=+[]{}<>:?",
                        },
                        "providerConfigRef": {
                            "name": "creds-provider",
                        },
                    },
                },
            )

        # 15. Aurora PostgreSQL Cluster
        resource.update(
            rsp.desired.resources["aurora-cluster"],
            {
                "apiVersion": "rds.aws.upbound.io/v1beta1",
                "kind": "Cluster",
                "metadata": {
                    "annotations": {
                        "crossplane.io/external-name": "vector-db-cluster",
                    },
                },
                "spec": {
                    "forProvider": {
                        "region": location,
                        "engine": "aurora-postgresql",
                        "engineVersion": engine_version,
                        "masterUsername": master_username,
                        "masterPassword": "dummy-password",
                        "skipFinalSnapshot": False,
                        "deletionProtection": deletion_protection,
                        "storageEncrypted": True,
                        "copyTagsToSnapshot": True,
                        "backupRetentionPeriod": backup_retention_period,
                        "preferredBackupWindow": backup_window,
                        "preferredMaintenanceWindow": maintenance_window,
                        "monitoringInterval": 60,
                        "monitoringRoleArn": "dummy-monitoring-role",
                        "performanceInsightsEnabled": True,
                        "performanceInsightsRetentionPeriod": 7,
                        "dbClusterParameterGroupName": "dummy-cluster-parameter-group",
                        "vpcSecurityGroupIds": ["dummy-sg"],
                        "dbSubnetGroupName": "dummy-subnet-group",
                        "tags": {
                            "Name": "vector-db-cluster",
                        },
                    },
                    "providerConfigRef": {
                        "name": "creds-provider",
                    },
                },
            },
        )

        # 16. Aurora Serverless v2 Instance
        resource.update(
            rsp.desired.resources["aurora-instance"],
            {
                "apiVersion": "rds.aws.upbound.io/v1beta1",
                "kind": "Instance",
                "metadata": {
                    "annotations": {
                        "crossplane.io/external-name": "vector-db-instance",
                    },
                },
                "spec": {
                    "forProvider": {
                        "region": location,
                        "engine": "aurora-postgresql",
                        "instanceClass": "db.serverless",
                        "clusterIdentifier": "dummy-cluster",
                        "autoMinorVersionUpgrade": True,
                        "dbParameterGroupName": "dummy-parameter-group",
                        "monitoringInterval": 60,
                        "monitoringRoleArn": "dummy-monitoring-role",
                        "performanceInsightsEnabled": True,
                        "performanceInsightsRetentionPeriod": 7,
                        "serverlessV2ScalingConfiguration": {
                            "minCapacity": min_capacity,
                            "maxCapacity": max_capacity,
                        },
                        "tags": {
                            "Name": "vector-db-instance",
                        },
                    },
                    "providerConfigRef": {
                        "name": "creds-provider",
                    },
                },
            },
        )

        # 17. Secret for database credentials
        resource.update(
            rsp.desired.resources["db-secret"],
            {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {
                    "name": "vector-db-secret",
                    "annotations": {
                        "crossplane.io/external-name": "vector-db-secret",
                    },
                },
                "type": "Opaque",
                "stringData": {
                    "username": master_username,
                    "password": "dummy-password",
                    "endpoint": "dummy-endpoint",
                    "port": "5432",
                    "database": database_name,
                },
            },
        )

        log.info(
            "Created vector database infrastructure resources",
            resource_count=len(rsp.desired.resources),
        )

        return rsp
