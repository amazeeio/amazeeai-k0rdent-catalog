import unittest
from unittest.mock import Mock, patch

from crossplane.function import logging, resource
from crossplane.function.proto.v1 import run_function_pb2 as fnv1

from function.fn import FunctionRunner


class TestFunctionRunner(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        # Allow larger diffs, since we diff large strings of JSON.
        self.maxDiff = None

        logging.configure(level=logging.Level.DISABLED)

    @patch("function.fn.boto3")
    async def test_run_function_basic(self, mock_boto3) -> None:
        """
        Given a basic vector database request with minimal configuration
        When the function runs
        Then it should create AWS infrastructure and return a Kubernetes Secret
        """
        # Mock AWS clients
        mock_ec2_client = Mock()
        mock_rds_client = Mock()
        mock_iam_client = Mock()

        mock_boto3.client.side_effect = lambda service, _: {
            "ec2": mock_ec2_client,
            "rds": mock_rds_client,
            "iam": mock_iam_client
        }[service]

        # Mock VPC infrastructure creation
        mock_ec2_client.create_vpc.return_value = {"Vpc": {"VpcId": "vpc-12345"}}
        mock_ec2_client.create_internet_gateway.return_value = {
            "InternetGateway": {"InternetGatewayId": "igw-12345"}
        }
        mock_ec2_client.create_subnet.side_effect = [
            {"Subnet": {"SubnetId": f"subnet-{i}"}} for i in range(1, 5)
        ]
        mock_ec2_client.create_route_table.return_value = {
            "RouteTable": {"RouteTableId": "rt-12345"}
        }
        mock_ec2_client.describe_subnets.return_value = {
            "Subnets": [{"SubnetId": "subnet-1"}, {"SubnetId": "subnet-2"}]
        }

        # Mock security group creation
        mock_ec2_client.create_security_group.return_value = {"GroupId": "sg-12345"}

        # Mock IAM role creation
        mock_iam_client.create_role.return_value = {
            "Role": {"Arn": "arn:aws:iam::123456789012:role/vector-db-monitoring-role"}
        }

        # Mock RDS operations
        mock_rds_client.create_db_cluster_parameter_group.return_value = {}
        mock_rds_client.create_db_parameter_group.return_value = {}
        mock_rds_client.create_db_subnet_group.return_value = {}
        mock_rds_client.create_db_cluster.return_value = {}
        mock_rds_client.create_db_instance.return_value = {}

        req = fnv1.RunFunctionRequest(
            input=resource.dict_to_struct({"version": "v1beta2"}),
            observed=fnv1.State(
                composite=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {
                            "apiVersion": "example.crossplane.io/v1",
                            "kind": "VectorDatabase",
                            "spec": {
                                "location": "us-west-2",
                            },
                        }
                    ),
                ),
            ),
        )

        runner = FunctionRunner()
        got = await runner.RunFunction(req, None)

        # Check that we get a Kubernetes Secret
        self.assertIn("db-secret", got.desired.resources)

        secret = got.desired.resources["db-secret"]
        self.assertEqual(secret.resource["apiVersion"], "v1")
        self.assertEqual(secret.resource["kind"], "Secret")
        self.assertEqual(secret.resource["metadata"]["name"], "vector-db-secret")

        # Check secret data
        string_data = secret.resource["stringData"]
        self.assertEqual(string_data["username"], "postgres")
        self.assertEqual(string_data["database"], "vectordb")
        self.assertEqual(string_data["port"], "5432")
        self.assertIn("password", string_data)
        self.assertIn("endpoint", string_data)

        # Check that TTL is set
        self.assertEqual(got.meta.ttl.seconds, 60)

        # Verify AWS clients were called
        mock_boto3.client.assert_any_call("ec2", region_name="us-west-2")
        mock_boto3.client.assert_any_call("rds", region_name="us-west-2")
        mock_boto3.client.assert_any_call("iam", region_name="us-west-2")

    @patch("function.fn.boto3")
    async def test_run_function_with_custom_config(self, mock_boto3) -> None:
        """
        Given a vector database request with custom configuration
        When the function runs
        Then it should create AWS infrastructure with custom settings
        """
        # Mock AWS clients
        mock_ec2_client = Mock()
        mock_rds_client = Mock()
        mock_iam_client = Mock()

        mock_boto3.client.side_effect = lambda service, _: {
            "ec2": mock_ec2_client,
            "rds": mock_rds_client,
            "iam": mock_iam_client
        }[service]

        # Mock VPC infrastructure creation
        mock_ec2_client.create_vpc.return_value = {"Vpc": {"VpcId": "vpc-12345"}}
        mock_ec2_client.create_internet_gateway.return_value = {
            "InternetGateway": {"InternetGatewayId": "igw-12345"}
        }
        mock_ec2_client.create_subnet.side_effect = [
            {"Subnet": {"SubnetId": f"subnet-{i}"}} for i in range(1, 5)
        ]
        mock_ec2_client.create_route_table.return_value = {
            "RouteTable": {"RouteTableId": "rt-12345"}
        }
        mock_ec2_client.describe_subnets.return_value = {
            "Subnets": [{"SubnetId": "subnet-1"}, {"SubnetId": "subnet-2"}]
        }

        # Mock security group creation
        mock_ec2_client.create_security_group.return_value = {"GroupId": "sg-12345"}

        # Mock IAM role creation
        mock_iam_client.create_role.return_value = {
            "Role": {"Arn": "arn:aws:iam::123456789012:role/vector-db-monitoring-role"}
        }

        # Mock RDS operations
        mock_rds_client.create_db_cluster_parameter_group.return_value = {}
        mock_rds_client.create_db_parameter_group.return_value = {}
        mock_rds_client.create_db_subnet_group.return_value = {}
        mock_rds_client.create_db_cluster.return_value = {}
        mock_rds_client.create_db_instance.return_value = {}

        req = fnv1.RunFunctionRequest(
            input=resource.dict_to_struct({"version": "v1beta2"}),
            observed=fnv1.State(
                composite=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {
                            "apiVersion": "example.crossplane.io/v1",
                            "kind": "VectorDatabase",
                            "spec": {
                                "location": "eu-central-1",
                                "engineVersion": "16.7",
                                "minCapacity": 4,
                                "maxCapacity": 32,
                                "databaseName": "myvectordb",
                                "masterUsername": "admin",
                                "backupRetentionPeriod": 14,
                                "backupWindow": "03:00-03:30",
                                "maintenanceWindow": "sun:02:00-sun:03:00",
                                "deletionProtection": False,
                                "generatePassword": False,
                            },
                        }
                    ),
                ),
            ),
        )

        runner = FunctionRunner()
        got = await runner.RunFunction(req, None)

        # Check that RDS cluster was created with custom settings
        mock_rds_client.create_db_cluster.assert_called_once()
        cluster_call_args = mock_rds_client.create_db_cluster.call_args[1]
        self.assertEqual(cluster_call_args["EngineVersion"], "16.7")
        self.assertEqual(cluster_call_args["MasterUsername"], "admin")
        self.assertEqual(cluster_call_args["BackupRetentionPeriod"], 14)
        self.assertEqual(cluster_call_args["PreferredBackupWindow"], "03:00-03:30")
        self.assertEqual(
            cluster_call_args["PreferredMaintenanceWindow"], "sun:02:00-sun:03:00"
        )
        self.assertEqual(cluster_call_args["DeletionProtection"], False)

        # Check that RDS instance was created with custom scaling
        mock_rds_client.create_db_instance.assert_called_once()
        instance_call_args = mock_rds_client.create_db_instance.call_args[1]
        scaling_config = instance_call_args["ServerlessV2ScalingConfiguration"]
        self.assertEqual(scaling_config["MinCapacity"], 4)
        self.assertEqual(scaling_config["MaxCapacity"], 32)

        # Check secret data reflects custom settings
        secret = got.desired.resources["db-secret"]
        string_data = secret.resource["stringData"]
        self.assertEqual(string_data["username"], "admin")
        self.assertEqual(string_data["database"], "myvectordb")

    @patch("function.fn.boto3")
    async def test_availability_zone_mapping(self, mock_boto3) -> None:
        """
        Given different regions
        When the function creates subnets
        Then it should use the correct availability zone mapping
        """
        regions_to_test = [
            "eu-central-2",
            "eu-west-2",
            "eu-central-1",
            "us-east-1",
            "us-east-2",
            "ap-southeast-2",
            "ca-central-1",
            "af-south-1",
        ]

        for region in regions_to_test:
            # Mock AWS clients
            mock_ec2_client = Mock()
            mock_rds_client = Mock()
            mock_iam_client = Mock()

            # Create a closure to capture the current mock clients
            def create_client_mapping(service, _, ec2=mock_ec2_client, rds=mock_rds_client, iam=mock_iam_client):
                return {
                    "ec2": ec2,
                    "rds": rds,
                    "iam": iam
                }[service]

            mock_boto3.client.side_effect = create_client_mapping

            # Mock VPC infrastructure creation
            mock_ec2_client.create_vpc.return_value = {"Vpc": {"VpcId": "vpc-12345"}}
            mock_ec2_client.create_internet_gateway.return_value = {
                "InternetGateway": {"InternetGatewayId": "igw-12345"}
            }
            mock_ec2_client.create_subnet.side_effect = [
                {"Subnet": {"SubnetId": f"subnet-{i}"}} for i in range(1, 5)
            ]
            mock_ec2_client.create_route_table.return_value = {
                "RouteTable": {"RouteTableId": "rt-12345"}
            }
            mock_ec2_client.describe_subnets.return_value = {
                "Subnets": [{"SubnetId": "subnet-1"}, {"SubnetId": "subnet-2"}]
            }

            # Mock security group creation
            mock_ec2_client.create_security_group.return_value = {"GroupId": "sg-12345"}

            # Mock IAM role creation
            mock_iam_client.create_role.return_value = {
                "Role": {
                    "Arn": "arn:aws:iam::123456789012:role/vector-db-monitoring-role"
                }
            }

            # Mock RDS operations
            mock_rds_client.create_db_cluster_parameter_group.return_value = {}
            mock_rds_client.create_db_parameter_group.return_value = {}
            mock_rds_client.create_db_subnet_group.return_value = {}
            mock_rds_client.create_db_cluster.return_value = {}
            mock_rds_client.create_db_instance.return_value = {}

            req = fnv1.RunFunctionRequest(
                input=resource.dict_to_struct({"version": "v1beta2"}),
                observed=fnv1.State(
                    composite=fnv1.Resource(
                        resource=resource.dict_to_struct(
                            {
                                "apiVersion": "example.crossplane.io/v1",
                                "kind": "VectorDatabase",
                                "spec": {
                                    "location": region,
                                },
                            }
                        ),
                    ),
                ),
            )

            runner = FunctionRunner()
            await runner.RunFunction(req, None)

            # Check that subnets were created with correct AZ mapping
            subnet_calls = mock_ec2_client.create_subnet.call_args_list
            self.assertEqual(len(subnet_calls), 4)  # 2 public + 2 private subnets

            # Check first subnet (public subnet 1) uses 'a' suffix
            first_subnet_call = subnet_calls[0][1]
            expected_az_a = f"{region}a"
            self.assertEqual(first_subnet_call["AvailabilityZone"], expected_az_a)

            # Check second subnet (private subnet 1) also uses 'a' suffix
            second_subnet_call = subnet_calls[1][1]
            self.assertEqual(second_subnet_call["AvailabilityZone"], expected_az_a)

            # Check third subnet (public subnet 2) uses 'b' suffix
            third_subnet_call = subnet_calls[2][1]
            expected_az_b = f"{region}b"
            self.assertEqual(third_subnet_call["AvailabilityZone"], expected_az_b)

            # Check fourth subnet (private subnet 2) also uses 'b' suffix
            fourth_subnet_call = subnet_calls[3][1]
            self.assertEqual(fourth_subnet_call["AvailabilityZone"], expected_az_b)

            # Reset mocks for next iteration
            mock_boto3.reset_mock()

    @patch("function.fn.boto3")
    async def test_default_values(self, mock_boto3) -> None:
        """
        Given a vector database request with minimal spec
        When the function runs
        Then it should use default values for optional parameters
        """
        # Mock AWS clients
        mock_ec2_client = Mock()
        mock_rds_client = Mock()
        mock_iam_client = Mock()

        mock_boto3.client.side_effect = lambda service, _: {
            "ec2": mock_ec2_client,
            "rds": mock_rds_client,
            "iam": mock_iam_client
        }[service]

        # Mock VPC infrastructure creation
        mock_ec2_client.create_vpc.return_value = {"Vpc": {"VpcId": "vpc-12345"}}
        mock_ec2_client.create_internet_gateway.return_value = {
            "InternetGateway": {"InternetGatewayId": "igw-12345"}
        }
        mock_ec2_client.create_subnet.side_effect = [
            {"Subnet": {"SubnetId": f"subnet-{i}"}} for i in range(1, 5)
        ]
        mock_ec2_client.create_route_table.return_value = {
            "RouteTable": {"RouteTableId": "rt-12345"}
        }
        mock_ec2_client.describe_subnets.return_value = {
            "Subnets": [{"SubnetId": "subnet-1"}, {"SubnetId": "subnet-2"}]
        }

        # Mock security group creation
        mock_ec2_client.create_security_group.return_value = {"GroupId": "sg-12345"}

        # Mock IAM role creation
        mock_iam_client.create_role.return_value = {
            "Role": {"Arn": "arn:aws:iam::123456789012:role/vector-db-monitoring-role"}
        }

        # Mock RDS operations
        mock_rds_client.create_db_cluster_parameter_group.return_value = {}
        mock_rds_client.create_db_parameter_group.return_value = {}
        mock_rds_client.create_db_subnet_group.return_value = {}
        mock_rds_client.create_db_cluster.return_value = {}
        mock_rds_client.create_db_instance.return_value = {}

        req = fnv1.RunFunctionRequest(
            input=resource.dict_to_struct({"version": "v1beta2"}),
            observed=fnv1.State(
                composite=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {
                            "apiVersion": "example.crossplane.io/v1",
                            "kind": "VectorDatabase",
                            "spec": {
                                "location": "us-west-2",
                            },
                        }
                    ),
                ),
            ),
        )

        runner = FunctionRunner()
        got = await runner.RunFunction(req, None)

        # Check that RDS cluster was created with default values
        mock_rds_client.create_db_cluster.assert_called_once()
        cluster_call_args = mock_rds_client.create_db_cluster.call_args[1]
        self.assertEqual(cluster_call_args["EngineVersion"], "16.6")
        self.assertEqual(cluster_call_args["MasterUsername"], "postgres")
        self.assertEqual(cluster_call_args["BackupRetentionPeriod"], 7)
        self.assertEqual(cluster_call_args["PreferredBackupWindow"], "06:42-07:12")
        self.assertEqual(
            cluster_call_args["PreferredMaintenanceWindow"], "wed:04:35-wed:05:05"
        )
        self.assertEqual(cluster_call_args["DeletionProtection"], True)

        # Check that RDS instance was created with default scaling
        mock_rds_client.create_db_instance.assert_called_once()
        instance_call_args = mock_rds_client.create_db_instance.call_args[1]
        scaling_config = instance_call_args["ServerlessV2ScalingConfiguration"]
        self.assertEqual(scaling_config["MinCapacity"], 2)
        self.assertEqual(scaling_config["MaxCapacity"], 16)

        # Check default database name in secret
        secret = got.desired.resources["db-secret"]
        self.assertEqual(secret.resource["stringData"]["database"], "vectordb")

    @patch("function.fn.boto3")
    async def test_resource_structure(self, mock_boto3) -> None:
        """
        Given a vector database request
        When the function runs
        Then the Kubernetes Secret should have the correct structure and metadata
        """
        # Mock AWS clients
        mock_ec2_client = Mock()
        mock_rds_client = Mock()
        mock_iam_client = Mock()

        mock_boto3.client.side_effect = lambda service, _: {
            "ec2": mock_ec2_client,
            "rds": mock_rds_client,
            "iam": mock_iam_client
        }[service]

        # Mock VPC infrastructure creation
        mock_ec2_client.create_vpc.return_value = {"Vpc": {"VpcId": "vpc-12345"}}
        mock_ec2_client.create_internet_gateway.return_value = {
            "InternetGateway": {"InternetGatewayId": "igw-12345"}
        }
        mock_ec2_client.create_subnet.side_effect = [
            {"Subnet": {"SubnetId": f"subnet-{i}"}} for i in range(1, 5)
        ]
        mock_ec2_client.create_route_table.return_value = {
            "RouteTable": {"RouteTableId": "rt-12345"}
        }
        mock_ec2_client.describe_subnets.return_value = {
            "Subnets": [{"SubnetId": "subnet-1"}, {"SubnetId": "subnet-2"}]
        }

        # Mock security group creation
        mock_ec2_client.create_security_group.return_value = {"GroupId": "sg-12345"}

        # Mock IAM role creation
        mock_iam_client.create_role.return_value = {
            "Role": {"Arn": "arn:aws:iam::123456789012:role/vector-db-monitoring-role"}
        }

        # Mock RDS operations
        mock_rds_client.create_db_cluster_parameter_group.return_value = {}
        mock_rds_client.create_db_parameter_group.return_value = {}
        mock_rds_client.create_db_subnet_group.return_value = {}
        mock_rds_client.create_db_cluster.return_value = {}
        mock_rds_client.create_db_instance.return_value = {}

        req = fnv1.RunFunctionRequest(
            input=resource.dict_to_struct({"version": "v1beta2"}),
            observed=fnv1.State(
                composite=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {
                            "apiVersion": "example.crossplane.io/v1",
                            "kind": "VectorDatabase",
                            "spec": {
                                "location": "us-west-2",
                            },
                        }
                    ),
                ),
            ),
        )

        runner = FunctionRunner()
        got = await runner.RunFunction(req, None)

        # Check that the secret has proper metadata and structure
        secret = got.desired.resources["db-secret"]

        # Check metadata
        self.assertIn("metadata", secret.resource)
        self.assertIn("annotations", secret.resource["metadata"])
        self.assertIn(
            "crossplane.io/external-name",
            secret.resource["metadata"]["annotations"],
        )

        # Check API version and kind
        self.assertEqual(secret.resource["apiVersion"], "v1")
        self.assertEqual(secret.resource["kind"], "Secret")

        # Check secret data structure
        self.assertIn("stringData", secret.resource)
        string_data = secret.resource["stringData"]
        required_fields = [
            "username", "password", "endpoint", "port", "database",
            "vpc_id", "subnet_group", "security_group"
        ]
        for field in required_fields:
            self.assertIn(field, string_data)

    @patch("function.fn.boto3")
    async def test_existing_vpc_usage(self, mock_boto3) -> None:
        """
        Given a vector database request with an existing VPC ID
        When the function runs
        Then it should use the existing VPC instead of creating new infrastructure
        """
        # Mock AWS clients
        mock_ec2_client = Mock()
        mock_rds_client = Mock()
        mock_iam_client = Mock()

        mock_boto3.client.side_effect = lambda service, _: {
            "ec2": mock_ec2_client,
            "rds": mock_rds_client,
            "iam": mock_iam_client
        }[service]

        # Mock existing VPC subnets
        mock_ec2_client.describe_subnets.return_value = {
            "Subnets": [
                {"SubnetId": "subnet-existing-1"},
                {"SubnetId": "subnet-existing-2"},
                {"SubnetId": "subnet-existing-3"}
            ]
        }

        # Mock security group creation
        mock_ec2_client.create_security_group.return_value = {"GroupId": "sg-12345"}

        # Mock IAM role creation
        mock_iam_client.create_role.return_value = {
            "Role": {"Arn": "arn:aws:iam::123456789012:role/vector-db-monitoring-role"}
        }

        # Mock RDS operations
        mock_rds_client.create_db_cluster_parameter_group.return_value = {}
        mock_rds_client.create_db_parameter_group.return_value = {}
        mock_rds_client.create_db_subnet_group.return_value = {}
        mock_rds_client.create_db_cluster.return_value = {}
        mock_rds_client.create_db_instance.return_value = {}

        req = fnv1.RunFunctionRequest(
            input=resource.dict_to_struct({"version": "v1beta2"}),
            observed=fnv1.State(
                composite=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {
                            "apiVersion": "example.crossplane.io/v1",
                            "kind": "VectorDatabase",
                            "spec": {
                                "location": "us-west-2",
                                "vpcId": "vpc-existing-12345",
                            },
                        }
                    ),
                ),
            ),
        )

        runner = FunctionRunner()
        got = await runner.RunFunction(req, None)

        # Check that describe_subnets was called with the existing VPC
        mock_ec2_client.describe_subnets.assert_called_once()
        call_args = mock_ec2_client.describe_subnets.call_args[1]
        self.assertIn(
            {"Name": "vpc-id", "Values": ["vpc-existing-12345"]}, call_args["Filters"]
        )

        # Check that VPC creation was not called
        mock_ec2_client.create_vpc.assert_not_called()

        # Check that subnet group was created with existing subnets
        mock_rds_client.create_db_subnet_group.assert_called_once()
        subnet_group_call_args = mock_rds_client.create_db_subnet_group.call_args[1]
        self.assertEqual(
            subnet_group_call_args["SubnetIds"],
            ["subnet-existing-1", "subnet-existing-2"]
        )

        # Check secret contains the existing VPC ID
        secret = got.desired.resources["db-secret"]
        self.assertEqual(secret.resource["stringData"]["vpc_id"], "vpc-existing-12345")


if __name__ == "__main__":
    unittest.main()
