"""A Crossplane composition function for creating vector database infrastructure using AWS SDK."""

import json
import secrets
import string
from typing import Any

import boto3
import grpc
from crossplane.function import logging, resource, response
from crossplane.function.proto.v1 import run_function_pb2 as fnv1
from crossplane.function.proto.v1 import run_function_pb2_grpc as grpcv1
from google.protobuf import json_format

# Constants
MIN_SUBNETS_REQUIRED = 2


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

    def _create_vpc_infrastructure(
        self, ec2_client, location: str
    ) -> dict[str, str]:
        """Create VPC infrastructure and return resource IDs."""
        self.log.info("Creating VPC infrastructure")

        # Create VPC
        vpc_response = ec2_client.create_vpc(
            CidrBlock="10.0.0.0/16",
            EnableDnsHostnames=True,
            EnableDnsSupport=True,
            TagSpecifications=[
                {
                    "ResourceType": "vpc",
                    "Tags": [{"Key": "Name", "Value": "vector-db-vpc"}]
                }
            ]
        )
        vpc_id = vpc_response["Vpc"]["VpcId"]

        # Create Internet Gateway
        igw_response = ec2_client.create_internet_gateway(
            TagSpecifications=[
                {
                    "ResourceType": "internet-gateway",
                    "Tags": [{"Key": "Name", "Value": "vector-db-igw"}]
                }
            ]
        )
        igw_id = igw_response["InternetGateway"]["InternetGatewayId"]

        # Attach Internet Gateway to VPC
        ec2_client.attach_internet_gateway(
            InternetGatewayId=igw_id,
            VpcId=vpc_id
        )

        # Create subnets
        subnet_ids = []
        for i, az_suffix in enumerate(["a", "b"]):
            az = self._get_availability_zone(location, az_suffix)

            # Public subnet
            public_subnet_response = ec2_client.create_subnet(
                VpcId=vpc_id,
                CidrBlock=f"10.0.{i+1}.0/24",
                AvailabilityZone=az,
                MapPublicIpOnLaunch=True,
                TagSpecifications=[
                    {
                        "ResourceType": "subnet",
                        "Tags": [
                            {"Key": "Name", "Value": f"vector-db-public-subnet-{i+1}"}
                        ]
                    }
                ]
            )
            public_subnet_id = public_subnet_response["Subnet"]["SubnetId"]
            subnet_ids.append(public_subnet_id)

            # Private subnet (for database)
            private_subnet_response = ec2_client.create_subnet(
                VpcId=vpc_id,
                CidrBlock=f"10.0.{i+3}.0/24",
                AvailabilityZone=az,
                TagSpecifications=[
                    {
                        "ResourceType": "subnet",
                        "Tags": [
                            {"Key": "Name", "Value": f"vector-db-private-subnet-{i+1}"}
                        ]
                    }
                ]
            )
            private_subnet_id = private_subnet_response["Subnet"]["SubnetId"]
            subnet_ids.append(private_subnet_id)

        # Create route table for public subnets
        route_table_response = ec2_client.create_route_table(
            VpcId=vpc_id,
            TagSpecifications=[
                {
                    "ResourceType": "route-table",
                    "Tags": [{"Key": "Name", "Value": "vector-db-public-rt"}]
                }
            ]
        )
        route_table_id = route_table_response["RouteTable"]["RouteTableId"]

        # Add route to internet gateway
        ec2_client.create_route(
            RouteTableId=route_table_id,
            DestinationCidrBlock="0.0.0.0/0",
            GatewayId=igw_id
        )

        # Associate route table with public subnets
        for i in range(2):
            ec2_client.associate_route_table(
                RouteTableId=route_table_id,
                SubnetId=ec2_client.describe_subnets(
                    Filters=[
                        {"Name": "vpc-id", "Values": [vpc_id]},
                        {
                            "Name": "tag:Name",
                            "Values": [f"vector-db-public-subnet-{i+1}"]
                        }
                    ]
                )["Subnets"][0]["SubnetId"]
            )

        return {
            "vpc_id": vpc_id,
            "subnet_ids": subnet_ids,
            "igw_id": igw_id,
            "route_table_id": route_table_id
        }

    def _create_security_group(self, ec2_client, vpc_id: str) -> str:
        """Create security group for Aurora and return its ID."""
        self.log.info("Creating security group for Aurora")

        sg_response = ec2_client.create_security_group(
            GroupName="vector-db-aurora-sg",
            Description="Security group for Aurora PostgreSQL cluster",
            VpcId=vpc_id,
            TagSpecifications=[
                {
                    "ResourceType": "security-group",
                    "Tags": [{"Key": "Name", "Value": "vector-db-aurora-sg"}]
                }
            ]
        )
        sg_id = sg_response["GroupId"]

        # Add ingress rule for PostgreSQL
        ec2_client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 5432,
                    "ToPort": 5432,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}]
                }
            ]
        )

        return sg_id

    def _create_iam_role(self, iam_client) -> str:
        """Create IAM role for RDS monitoring and return its ARN."""
        self.log.info("Creating IAM role for RDS monitoring")

        trust_policy = {
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
        }

        role_response = iam_client.create_role(
            RoleName="vector-db-monitoring-role",
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Role for RDS enhanced monitoring",
            Tags=[
                {"Key": "Name", "Value": "vector-db-monitoring-role"}
            ]
        )

        # Attach the RDS enhanced monitoring policy
        iam_client.attach_role_policy(
            RoleName="vector-db-monitoring-role",
            PolicyArn="arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
        )

        return role_response["Role"]["Arn"]

    def _create_parameter_groups(self, rds_client) -> dict[str, str]:
        """Create parameter groups for vector extension and return their names."""
        self.log.info("Creating parameter groups for vector extension")

        # Create cluster parameter group
        rds_client.create_db_cluster_parameter_group(
            DBClusterParameterGroupName="vector-db-cluster-parameter-group",
            DBParameterGroupFamily="aurora-postgresql16",
            Description="Cluster parameter group for vector extension",
            Tags=[
                {"Key": "Name", "Value": "vector-db-cluster-parameter-group"}
            ]
        )

        # Create instance parameter group
        rds_client.create_db_parameter_group(
            DBParameterGroupName="vector-db-parameter-group",
            DBParameterGroupFamily="aurora-postgresql16",
            Description="Parameter group for vector extension",
            Tags=[
                {"Key": "Name", "Value": "vector-db-parameter-group"}
            ]
        )

        # Modify cluster parameter group to include vector extension
        rds_client.modify_db_cluster_parameter_group(
            DBClusterParameterGroupName="vector-db-cluster-parameter-group",
            Parameters=[
                {
                    "ParameterName": "shared_preload_libraries",
                    "ParameterValue": "vector",
                    "ApplyMethod": "pending-reboot"
                }
            ]
        )

        # Modify instance parameter group to include vector extension
        rds_client.modify_db_parameter_group(
            DBParameterGroupName="vector-db-parameter-group",
            Parameters=[
                {
                    "ParameterName": "shared_preload_libraries",
                    "ParameterValue": "vector",
                    "ApplyMethod": "pending-reboot"
                }
            ]
        )

        return {
            "cluster_parameter_group": "vector-db-cluster-parameter-group",
            "instance_parameter_group": "vector-db-parameter-group"
        }

    def _create_subnet_group(self, rds_client, subnet_ids: list) -> str:
        """Create DB subnet group and return its name."""
        self.log.info("Creating DB subnet group")

        rds_client.create_db_subnet_group(
            DBSubnetGroupName="vector-db-subnet-group",
            DBSubnetGroupDescription="Subnet group for vector database",
            SubnetIds=subnet_ids,
            Tags=[
                {"Key": "Name", "Value": "vector-db-subnet-group"}
            ]
        )

        return "vector-db-subnet-group"

    def _create_aurora_cluster(
        self, rds_client, sg_id: str, subnet_group_name: str,
        parameter_groups: dict[str, str], monitoring_role_arn: str,
        config: dict[str, Any]
    ) -> dict[str, str]:
        """Create Aurora PostgreSQL cluster and return cluster and instance identifiers."""
        self.log.info("Creating Aurora PostgreSQL cluster")

        # Generate password if requested
        if config.get("generatePassword", True):
            alphabet = string.ascii_letters + string.digits + "!#$%&*()-_=+[]{}<>:?"
            master_password = "".join(secrets.choice(alphabet) for _ in range(16))
        else:
            master_password = "dummy-password"  # nosec: B105

        # Create cluster
        rds_client.create_db_cluster(
            DBClusterIdentifier="vector-db-cluster",
            Engine="aurora-postgresql",
            EngineVersion=config.get("engineVersion", "16.6"),
            MasterUsername=config.get("masterUsername", "postgres"),
            MasterUserPassword=master_password,
            SkipFinalSnapshot=False,
            DeletionProtection=config.get("deletionProtection", True),
            StorageEncrypted=True,
            CopyTagsToSnapshot=True,
            BackupRetentionPeriod=config.get("backupRetentionPeriod", 7),
            PreferredBackupWindow=config.get("backupWindow", "06:42-07:12"),
            PreferredMaintenanceWindow=config.get(
                "maintenanceWindow", "wed:04:35-wed:05:05"
            ),
            MonitoringInterval=60,
            MonitoringRoleArn=monitoring_role_arn,
            PerformanceInsightsEnabled=True,
            PerformanceInsightsRetentionPeriod=7,
            DBClusterParameterGroupName=parameter_groups["cluster_parameter_group"],
            VpcSecurityGroupIds=[sg_id],
            DBSubnetGroupName=subnet_group_name,
            Tags=[
                {"Key": "Name", "Value": "vector-db-cluster"}
            ]
        )

        # Create instance
        rds_client.create_db_instance(
            DBInstanceIdentifier="vector-db-instance",
            DBClusterIdentifier="vector-db-cluster",
            Engine="aurora-postgresql",
            DBInstanceClass="db.serverless",
            AutoMinorVersionUpgrade=True,
            DBParameterGroupName=parameter_groups["instance_parameter_group"],
            MonitoringInterval=60,
            MonitoringRoleArn=monitoring_role_arn,
            PerformanceInsightsEnabled=True,
            PerformanceInsightsRetentionPeriod=7,
            ServerlessV2ScalingConfiguration={
                "MinCapacity": config.get("minCapacity", 2),
                "MaxCapacity": config.get("maxCapacity", 16)
            },
            Tags=[
                {"Key": "Name", "Value": "vector-db-instance"}
            ]
        )

        return {
            "cluster_identifier": "vector-db-cluster",
            "instance_identifier": "vector-db-instance",
            "master_password": master_password
        }

    async def RunFunction(
        self, req: fnv1.RunFunctionRequest, _: grpc.aio.ServicerContext
    ) -> fnv1.RunFunctionResponse:
        """Run the function to create vector database infrastructure using AWS SDK."""
        log = self.log.bind(tag=req.meta.tag)
        log.info("Running vector database function with AWS SDK")

        rsp = response.to(req)

        # Extract configuration from the composite resource
        spec_dict = json_format.MessageToDict(req.observed.composite.resource["spec"])
        location = spec_dict["location"]
        vpc_id = spec_dict.get("vpcId")  # Optional VPC ID to use existing VPC

        config = {
            "engineVersion": spec_dict.get("engineVersion", "16.6"),
            "minCapacity": spec_dict.get("minCapacity", 2),
            "maxCapacity": spec_dict.get("maxCapacity", 16),
            "databaseName": spec_dict.get("databaseName", "vectordb"),
            "masterUsername": spec_dict.get("masterUsername", "postgres"),
            "backupRetentionPeriod": spec_dict.get("backupRetentionPeriod", 7),
            "backupWindow": spec_dict.get("backupWindow", "06:42-07:12"),
            "maintenanceWindow": spec_dict.get(
                "maintenanceWindow", "wed:04:35-wed:05:05"
            ),
            "deletionProtection": spec_dict.get("deletionProtection", True),
            "generatePassword": spec_dict.get("generatePassword", True)
        }

        log.info(
            "Creating vector database infrastructure using AWS SDK",
            location=location,
            vpc_id=vpc_id,
            engine_version=config["engineVersion"],
        )

        try:
            # Initialize AWS clients
            ec2_client = boto3.client("ec2", region_name=location)
            rds_client = boto3.client("rds", region_name=location)
            iam_client = boto3.client("iam", region_name=location)

            # Determine VPC and subnet configuration
            if vpc_id:
                # Use existing VPC
                log.info(f"Using existing VPC: {vpc_id}")

                # Get subnets from existing VPC
                subnets_response = ec2_client.describe_subnets(
                    Filters=[
                        {"Name": "vpc-id", "Values": [vpc_id]},
                        {"Name": "state", "Values": ["available"]}
                    ]
                )
                subnet_ids = [
                    subnet["SubnetId"] for subnet in subnets_response["Subnets"]
                ]

                if len(subnet_ids) < MIN_SUBNETS_REQUIRED:
                    error_msg = (
                        f"VPC {vpc_id} must have at least "
                        f"{MIN_SUBNETS_REQUIRED} subnets for RDS"
                    )
                    raise ValueError(error_msg)

                # Use first 2 subnets for the subnet group
                subnet_ids = subnet_ids[:MIN_SUBNETS_REQUIRED]

            else:
                # Create new VPC infrastructure
                log.info("Creating new VPC infrastructure")
                vpc_resources = self._create_vpc_infrastructure(ec2_client, location)
                vpc_id = vpc_resources["vpc_id"]
                subnet_ids = vpc_resources["subnet_ids"]

            # Create security group
            sg_id = self._create_security_group(ec2_client, vpc_id)

            # Create IAM role for monitoring
            monitoring_role_arn = self._create_iam_role(iam_client)

            # Create parameter groups
            parameter_groups = self._create_parameter_groups(rds_client)

            # Create subnet group
            subnet_group_name = self._create_subnet_group(rds_client, subnet_ids)

            # Create Aurora cluster
            aurora_resources = self._create_aurora_cluster(
                rds_client, sg_id, subnet_group_name,
                parameter_groups, monitoring_role_arn, config
            )

            # Create Kubernetes Secret for database credentials
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
                        "username": config["masterUsername"],
                        "password": aurora_resources["master_password"],
                        "endpoint": (
                            f"{aurora_resources['cluster_identifier']}."
                            f"cluster-{location}.rds.amazonaws.com"
                        ),
                        "port": "5432",
                        "database": config["databaseName"],
                        "vpc_id": vpc_id,
                        "subnet_group": subnet_group_name,
                        "security_group": sg_id,
                    },
                },
            )

            log.info(
                "Successfully created vector database infrastructure using AWS SDK",
                cluster_identifier=aurora_resources["cluster_identifier"],
                vpc_id=vpc_id,
                resource_count=len(rsp.desired.resources),
            )

        except Exception as e:
            log.error(f"Error creating vector database infrastructure: {e!s}")
            # Add error status to response
            rsp.results.append({
                "severity": "FATAL",
                "message": f"Failed to create vector database infrastructure: {e!s}"
            })

        return rsp
