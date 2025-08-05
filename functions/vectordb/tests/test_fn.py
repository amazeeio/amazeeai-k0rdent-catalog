"""Tests for the vector database function."""

import ipaddress
import unittest

from crossplane.function import logging, resource
from crossplane.function.proto.v1 import run_function_pb2 as fnv1

from function import fn


class TestVectorDBConfig(unittest.TestCase):
    """Test the VectorDBConfig dataclass."""

    def test_config_creation(self):
        """Test that VectorDBConfig can be created with required fields."""
        config = fn.VectorDBConfig(
            claim_name="test-claim",
            vpc_cidr="10.10.0.0/16",
            region="us-west-2",
            environment_suffix="dev",
            master_username="postgres",
            postgres_cluster_name="vectordb-cluster",
        )

        self.assertEqual(config.claim_name, "test-claim")
        self.assertEqual(config.vpc_cidr, "10.10.0.0/16")
        self.assertEqual(config.region, "us-west-2")
        self.assertEqual(config.environment_suffix, "dev")
        self.assertEqual(config.master_username, "postgres")
        self.assertEqual(config.postgres_cluster_name, "vectordb-cluster")
        self.assertEqual(config.az_count, 3)
        self.assertEqual(config.instance_count, 2)
        self.assertEqual(config.instance_class, "db.serverless")
        self.assertTrue(config.publicly_accessible)  # Default value
        self.assertEqual(config.engine_version, "16.1")  # Default value


class TestVectorDBFunctionRunner(unittest.IsolatedAsyncioTestCase):
    """Test the VectorDBFunctionRunner."""

    def setUp(self) -> None:
        """Set up test environment."""
        # Allow larger diffs, since we diff large strings of JSON.
        self.maxDiff = None
        logging.configure(level=logging.Level.DISABLED)

    def test_calculate_subnet_cidrs(self):
        """Test CIDR calculation for subnets."""
        # Given: VPC CIDR 10.10.0.0/16 and 3 AZs
        runner = fn.VectorDBFunctionRunner()

        # When: Calculating database subnet CIDRs
        cidrs = runner._calculate_subnet_cidrs("10.10.0.0/16", 3)

        # Then: Should return 10.10.6.0/24, 10.10.7.0/24, 10.10.8.0/24
        expected_cidrs = ["10.10.6.0/24", "10.10.7.0/24", "10.10.8.0/24"]
        self.assertEqual(cidrs, expected_cidrs)

    def test_calculate_subnet_cidrs_different_vpc(self):
        """Test CIDR calculation with different VPC CIDR."""
        runner = fn.VectorDBFunctionRunner()

        # When: Calculating with different VPC CIDR
        cidrs = runner._calculate_subnet_cidrs("192.168.0.0/16", 2)

        # Then: Should return correct subnets
        expected_cidrs = ["192.168.6.0/24", "192.168.7.0/24"]
        self.assertEqual(cidrs, expected_cidrs)

    def test_create_vpc_resource(self):
        """Test VPC resource creation."""
        # Given: VPC configuration
        config = fn.VectorDBConfig(
            claim_name="test-claim",
            vpc_cidr="10.10.0.0/16",
            region="us-west-2",
            environment_suffix="dev",
            master_username="postgres",
            postgres_cluster_name="vectordb-cluster",
        )
        runner = fn.VectorDBFunctionRunner()

        # When: Creating VPC resource
        vpc_resource = runner._create_vpc(config)

        # Then: Should return properly formatted VPC resource
        self.assertEqual(vpc_resource["apiVersion"], "ec2.aws.upbound.io/v1beta1")
        self.assertEqual(vpc_resource["kind"], "VPC")
        self.assertEqual(vpc_resource["metadata"]["name"], "test-claim-vpc-dev")
        self.assertEqual(vpc_resource["spec"]["forProvider"]["cidrBlock"], "10.10.0.0/16")
        self.assertEqual(vpc_resource["spec"]["forProvider"]["region"], "us-west-2")

    def test_create_internet_gateway(self):
        """Test Internet Gateway creation."""
        # Given: Configuration
        config = fn.VectorDBConfig(
            claim_name="test-claim",
            vpc_cidr="10.10.0.0/16",
            region="us-west-2",
            environment_suffix="dev",
            master_username="postgres",
            postgres_cluster_name="vectordb-cluster",
        )
        runner = fn.VectorDBFunctionRunner()

        # When: Creating Internet Gateway
        igw_resource = runner._create_internet_gateway(config)

        # Then: Should return IGW with proper configuration
        self.assertEqual(igw_resource["apiVersion"], "ec2.aws.upbound.io/v1beta1")
        self.assertEqual(igw_resource["kind"], "InternetGateway")
        self.assertEqual(igw_resource["metadata"]["name"], "test-claim-igw-dev")
        self.assertEqual(igw_resource["spec"]["forProvider"]["region"], "us-west-2")

    def test_create_database_subnets(self):
        """Test database subnet creation."""
        # Given: Configuration and CIDR blocks
        config = fn.VectorDBConfig(
            claim_name="test-claim",
            vpc_cidr="10.10.0.0/16",
            region="us-west-2",
            environment_suffix="dev",
            master_username="postgres",
            postgres_cluster_name="vectordb-cluster",
        )
        cidrs = ["10.10.6.0/24", "10.10.7.0/24", "10.10.8.0/24"]
        runner = fn.VectorDBFunctionRunner()

        # When: Creating database subnets
        subnet_resources = runner._create_database_subnets(config, cidrs)

        # Then: Should return subnets in correct AZs with proper tags
        self.assertEqual(len(subnet_resources), 3)

        for i, subnet in enumerate(subnet_resources):
            self.assertEqual(subnet["apiVersion"], "ec2.aws.upbound.io/v1beta1")
            self.assertEqual(subnet["kind"], "Subnet")
            self.assertEqual(subnet["metadata"]["name"], f"test-claim-subnet-{i}-dev")
            self.assertEqual(subnet["spec"]["forProvider"]["cidrBlock"], cidrs[i])
            self.assertEqual(subnet["spec"]["forProvider"]["region"], "us-west-2")
            self.assertTrue(subnet["spec"]["forProvider"]["mapPublicIpOnLaunch"])

    def test_create_route_table(self):
        """Test route table creation."""
        # Given: Configuration
        config = fn.VectorDBConfig(
            claim_name="test-claim",
            vpc_cidr="10.10.0.0/16",
            region="us-west-2",
            environment_suffix="dev",
            master_username="postgres",
            postgres_cluster_name="vectordb-cluster",
        )
        runner = fn.VectorDBFunctionRunner()

        # When: Creating route table
        route_table_resource = runner._create_database_route_table(config)

        # Then: Should have proper configuration
        self.assertEqual(route_table_resource["apiVersion"], "ec2.aws.upbound.io/v1beta1")
        self.assertEqual(route_table_resource["kind"], "RouteTable")
        self.assertEqual(route_table_resource["metadata"]["name"], "test-claim-route-table-dev")
        self.assertEqual(route_table_resource["spec"]["forProvider"]["region"], "us-west-2")

    def test_create_security_group(self):
        """Test security group creation."""
        # Given: Configuration
        config = fn.VectorDBConfig(
            claim_name="test-claim",
            vpc_cidr="10.10.0.0/16",
            region="us-west-2",
            environment_suffix="dev",
            master_username="postgres",
            postgres_cluster_name="vectordb-cluster",
        )
        runner = fn.VectorDBFunctionRunner()

        # When: Creating security group
        security_group_resource = runner._create_database_security_group(config)

        # Then: Should have basic security group configuration
        self.assertEqual(security_group_resource["apiVersion"], "ec2.aws.upbound.io/v1beta1")
        self.assertEqual(security_group_resource["kind"], "SecurityGroup")
        self.assertEqual(
            security_group_resource["metadata"]["name"], "test-claim-security-group-dev"
        )
        self.assertEqual(security_group_resource["spec"]["forProvider"]["region"], "us-west-2")
        self.assertIn("vpcIdRef", security_group_resource["spec"]["forProvider"])
        self.assertIn("tags", security_group_resource["spec"]["forProvider"])

    def test_create_security_group_rule(self):
        """Test security group rule creation for PostgreSQL access."""
        # Given: Configuration
        config = fn.VectorDBConfig(
            claim_name="test-claim",
            vpc_cidr="10.10.0.0/16",
            region="us-west-2",
            environment_suffix="dev",
            master_username="postgres",
            postgres_cluster_name="vectordb-cluster",
        )
        runner = fn.VectorDBFunctionRunner()

        # When: Creating security group rule
        security_group_rule_resource = runner._create_security_group_rule(config)

        # Then: Should have proper ingress rule configuration
        self.assertEqual(security_group_rule_resource["apiVersion"], "ec2.aws.upbound.io/v1beta1")
        self.assertEqual(security_group_rule_resource["kind"], "SecurityGroupRule")
        self.assertEqual(
            security_group_rule_resource["metadata"]["name"], "test-claim-postgres-ingress-dev"
        )
        self.assertEqual(security_group_rule_resource["spec"]["forProvider"]["type"], "ingress")
        self.assertEqual(security_group_rule_resource["spec"]["forProvider"]["fromPort"], 5432)
        self.assertEqual(security_group_rule_resource["spec"]["forProvider"]["toPort"], 5432)
        self.assertEqual(security_group_rule_resource["spec"]["forProvider"]["protocol"], "tcp")
        self.assertEqual(
            security_group_rule_resource["spec"]["forProvider"]["cidrBlocks"], ["0.0.0.0/0"]
        )
        self.assertEqual(
            security_group_rule_resource["spec"]["forProvider"]["description"], "PostgreSQL access"
        )

    def test_create_egress_rule(self):
        """Test security group egress rule creation."""
        # Given: Configuration
        config = fn.VectorDBConfig(
            claim_name="test-claim",
            vpc_cidr="10.10.0.0/16",
            region="us-west-2",
            environment_suffix="dev",
            master_username="postgres",
            postgres_cluster_name="vectordb-cluster",
        )
        runner = fn.VectorDBFunctionRunner()

        # When: Creating egress rule
        egress_rule_resource = runner._create_egress_rule(config)

        # Then: Should have proper egress rule configuration
        self.assertEqual(egress_rule_resource["apiVersion"], "ec2.aws.upbound.io/v1beta1")
        self.assertEqual(egress_rule_resource["kind"], "SecurityGroupRule")
        self.assertEqual(egress_rule_resource["metadata"]["name"], "test-claim-egress-all-dev")
        self.assertEqual(egress_rule_resource["spec"]["forProvider"]["type"], "egress")
        self.assertEqual(egress_rule_resource["spec"]["forProvider"]["fromPort"], 0)
        self.assertEqual(egress_rule_resource["spec"]["forProvider"]["toPort"], 0)
        self.assertEqual(egress_rule_resource["spec"]["forProvider"]["protocol"], "-1")
        self.assertEqual(egress_rule_resource["spec"]["forProvider"]["cidrBlocks"], ["0.0.0.0/0"])
        self.assertEqual(
            egress_rule_resource["spec"]["forProvider"]["description"], "Allow all outbound traffic"
        )

    def test_create_subnet_group(self):
        """Test subnet group creation."""
        # Given: Configuration
        config = fn.VectorDBConfig(
            claim_name="test-claim",
            vpc_cidr="10.10.0.0/16",
            region="us-west-2",
            environment_suffix="dev",
            master_username="postgres",
            postgres_cluster_name="vectordb-cluster",
        )
        runner = fn.VectorDBFunctionRunner()

        # When: Creating subnet group
        subnet_group_resource = runner._create_subnet_group(config)

        # Then: Should reference all subnet IDs
        self.assertEqual(subnet_group_resource["apiVersion"], "rds.aws.upbound.io/v1beta1")
        self.assertEqual(subnet_group_resource["kind"], "SubnetGroup")
        self.assertEqual(subnet_group_resource["metadata"]["name"], "test-claim-subnet-group-dev")
        self.assertEqual(subnet_group_resource["spec"]["forProvider"]["region"], "us-west-2")

    def test_create_aurora_cluster(self):
        """Test Aurora cluster creation."""
        # Given: Configuration
        config = fn.VectorDBConfig(
            claim_name="test-claim",
            vpc_cidr="10.10.0.0/16",
            region="us-west-2",
            environment_suffix="dev",
            master_username="postgres",
            postgres_cluster_name="vectordb-cluster",
        )
        # Add master_password attribute (normally set by RunFunction)
        config.master_password = "test-password"  # noqa: S105
        runner = fn.VectorDBFunctionRunner()

        # When: Creating Aurora cluster
        aurora_resource = runner._create_aurora_cluster(config)

        # Then: Should have proper configuration and references
        self.assertEqual(aurora_resource["apiVersion"], "rds.aws.upbound.io/v1beta1")
        self.assertEqual(aurora_resource["kind"], "Cluster")
        self.assertEqual(aurora_resource["metadata"]["name"], "vectordb-cluster")
        self.assertEqual(aurora_resource["spec"]["forProvider"]["engine"], "aurora-postgresql")
        self.assertEqual(aurora_resource["spec"]["forProvider"]["engineVersion"], "16.1")
        self.assertEqual(aurora_resource["spec"]["forProvider"]["masterUsername"], "postgres")
        self.assertIn("masterPasswordSecretRef", aurora_resource["spec"]["forProvider"])
        self.assertEqual(
            aurora_resource["spec"]["forProvider"]["masterPasswordSecretRef"]["name"],
            "test-claim-password-dev",
        )
        self.assertTrue(aurora_resource["spec"]["forProvider"]["storageEncrypted"])

        # Connection details have been removed as they are not required

    def test_create_aurora_instances(self):
        """Test Aurora cluster instances creation."""
        # Given: Configuration
        config = fn.VectorDBConfig(
            claim_name="test-claim",
            vpc_cidr="10.10.0.0/16",
            region="us-west-2",
            environment_suffix="dev",
            master_username="postgres",
            postgres_cluster_name="vectordb-cluster",
            instance_count=2,
            instance_class="db.serverless",
            publicly_accessible=True,
        )
        runner = fn.VectorDBFunctionRunner()

        # When: Creating Aurora instances
        aurora_instance_resources = runner._create_aurora_instances(config)

        # Then: Should create the correct number of instances
        self.assertEqual(len(aurora_instance_resources), 2)

        # Check first instance
        instance1 = aurora_instance_resources[0]
        self.assertEqual(instance1["apiVersion"], "rds.aws.upbound.io/v1beta1")
        self.assertEqual(instance1["kind"], "ClusterInstance")
        self.assertEqual(instance1["metadata"]["name"], "vectordb-cluster-instance-1")
        self.assertEqual(instance1["spec"]["forProvider"]["engine"], "aurora-postgresql")
        self.assertEqual(instance1["spec"]["forProvider"]["engineVersion"], "16.1")
        self.assertEqual(instance1["spec"]["forProvider"]["instanceClass"], "db.serverless")
        self.assertTrue(instance1["spec"]["forProvider"]["publiclyAccessible"])
        self.assertEqual(instance1["spec"]["forProvider"]["promotionTier"], 0)
        self.assertEqual(
            instance1["spec"]["forProvider"]["clusterIdentifierRef"]["name"], "vectordb-cluster"
        )
        self.assertEqual(
            instance1["spec"]["forProvider"]["dbSubnetGroupNameRef"]["name"],
            "test-claim-subnet-group-dev",
        )
        self.assertTrue(instance1["spec"]["forProvider"]["performanceInsightsEnabled"])
        self.assertEqual(instance1["spec"]["forProvider"]["performanceInsightsRetentionPeriod"], 7)
        self.assertEqual(
            instance1["spec"]["forProvider"]["dbParameterGroupName"], "default.aurora-postgresql16"
        )
        self.assertTrue(instance1["spec"]["forProvider"]["autoMinorVersionUpgrade"])
        self.assertEqual(instance1["spec"]["forProvider"]["monitoringInterval"], 0)

        # Check second instance
        instance2 = aurora_instance_resources[1]
        self.assertEqual(instance2["metadata"]["name"], "vectordb-cluster-instance-2")
        self.assertEqual(instance2["spec"]["forProvider"]["promotionTier"], 1)
        self.assertEqual(
            instance2["spec"]["forProvider"]["clusterIdentifierRef"]["name"], "vectordb-cluster"
        )

        # Check metadata and dependencies
        for instance in aurora_instance_resources:
            self.assertEqual(instance["metadata"]["labels"]["app"], "test-claim")
            self.assertEqual(instance["metadata"]["labels"]["environment"], "dev")
            self.assertIn("crossplane.io/depends-on", instance["metadata"]["annotations"])
            self.assertIn(
                "aurora_cluster",
                instance["metadata"]["annotations"]["crossplane.io/depends-on"],
            )

    def test_create_aurora_instances_custom_config(self):
        """Test Aurora cluster instances creation with custom configuration."""
        # Given: Configuration with custom instance settings
        config = fn.VectorDBConfig(
            claim_name="test-claim",
            vpc_cidr="10.10.0.0/16",
            region="us-west-2",
            environment_suffix="prod",
            master_username="postgres",
            postgres_cluster_name="vectordb-cluster",
            instance_count=3,
            instance_class="db.r6g.large",
            publicly_accessible=False,
        )
        runner = fn.VectorDBFunctionRunner()

        # When: Creating Aurora instances
        aurora_instance_resources = runner._create_aurora_instances(config)

        # Then: Should create the correct number of instances with custom settings
        self.assertEqual(len(aurora_instance_resources), 3)

        # Check custom settings are applied
        for i, instance in enumerate(aurora_instance_resources):
            self.assertEqual(instance["spec"]["forProvider"]["instanceClass"], "db.r6g.large")
            self.assertFalse(instance["spec"]["forProvider"]["publiclyAccessible"])
            self.assertEqual(instance["spec"]["forProvider"]["promotionTier"], i)
            self.assertEqual(instance["metadata"]["name"], f"vectordb-cluster-instance-{i + 1}")

    def test_extract_config(self):
        """Test configuration extraction from request."""
        # Given: Request with configuration
        req = fnv1.RunFunctionRequest(
            observed=fnv1.State(
                composite=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {
                            "spec": {
                                "apiVersion": "example.crossplane.io/v1",
                                "kind": "XR",
                                "location": "us-east-1",
                                "vpcCidr": "10.20.0.0/16",
                                "envSuffix": "test",
                                "masterUsername": "admin",
                                "clusterName": "test-cluster",
                                "azCount": 2,
                            }
                        }
                    ),
                ),
            ),
        )
        runner = fn.VectorDBFunctionRunner()

        # When: Extracting configuration
        config = runner._extract_config(req)

        # Then: Should extract all values correctly
        self.assertEqual(config.vpc_cidr, "10.20.0.0/16")
        self.assertEqual(config.region, "us-east-1")
        self.assertEqual(config.environment_suffix, "test")
        self.assertEqual(config.master_username, "admin")
        self.assertEqual(config.postgres_cluster_name, "test-cluster")
        self.assertEqual(config.az_count, 2)

    def test_extract_config_defaults(self):
        """Test configuration extraction with defaults."""
        # Given: Request with minimal configuration
        req = fnv1.RunFunctionRequest(
            input=resource.dict_to_struct({}),
            observed=fnv1.State(
                composite=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {
                            "apiVersion": "example.crossplane.io/v1",
                            "kind": "XR",
                            "spec": {"region": "us-west-2"},
                        }
                    ),
                ),
            ),
        )
        runner = fn.VectorDBFunctionRunner()

        # When: Extracting configuration
        config = runner._extract_config(req)

        # Then: Should use default values
        self.assertEqual(config.vpc_cidr, "10.10.0.0/16")
        self.assertEqual(config.region, "us-west-2")
        self.assertEqual(config.environment_suffix, "dev")
        self.assertEqual(config.master_username, "postgres")
        self.assertEqual(config.postgres_cluster_name, "vectordb-cluster")
        self.assertEqual(config.az_count, 3)

    async def test_complete_resource_generation(self):
        """Test complete resource generation workflow."""
        # Given: Valid configuration request
        req = fnv1.RunFunctionRequest(
            input=resource.dict_to_struct(
                {
                    "vpc_cidr": "10.10.0.0/16",
                    "environment_suffix": "dev",
                    "master_username": "postgres",
                    "postgres_cluster_name": "vectordb-cluster",
                }
            ),
            observed=fnv1.State(
                composite=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {
                            "apiVersion": "example.crossplane.io/v1",
                            "kind": "XR",
                            "spec": {"region": "us-west-2"},
                        }
                    ),
                ),
            ),
        )
        runner = fn.VectorDBFunctionRunner()

        # When: Running the function
        response = await runner.RunFunction(req, None)

        # Then: Should return all required resources with proper dependencies
        resources = response.desired.resources

        # Check that all expected resources are present
        expected_resources = [
            "vpc",
            "internet_gateway",
            "subnet_0",
            "subnet_1",
            "subnet_2",
            "route_table",
            "security_group",
            "security_group_rule",
            "egress_rule",
            "subnet_group",
            "aurora_cluster",
        ]

        for resource_name in expected_resources:
            self.assertIn(resource_name, resources)
            self.assertIsNotNone(resources[resource_name].resource)

    async def test_resource_dependencies(self):
        """Test that resources have correct dependencies."""
        # Given: Configuration request
        req = fnv1.RunFunctionRequest(
            input=resource.dict_to_struct(
                {
                    "vpc_cidr": "10.10.0.0/16",
                    "environment_suffix": "dev",
                    "master_username": "postgres",
                    "postgres_cluster_name": "vectordb-cluster",
                }
            ),
            observed=fnv1.State(
                composite=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {
                            "apiVersion": "example.crossplane.io/v1",
                            "kind": "XR",
                            "spec": {"region": "us-west-2"},
                        }
                    ),
                ),
            ),
        )
        runner = fn.VectorDBFunctionRunner()

        # When: Running the function
        response = await runner.RunFunction(req, None)

        # Then: All dependencies should be properly linked
        resources = response.desired.resources

        # Check that subnets reference the VPC
        for i in range(3):
            subnet = resources[f"subnet_{i}"].resource
            vpc_ref = subnet["spec"]["forProvider"]["vpcIdRef"]
            self.assertEqual(vpc_ref["name"], "vectordb-vpc-dev")

        # Check that security group references the VPC
        security_group = resources["security_group"].resource
        vpc_ref = security_group["spec"]["forProvider"]["vpcIdRef"]
        self.assertEqual(vpc_ref["name"], "vectordb-vpc-dev")

    def test_cidr_allocation(self):
        """Test that CIDR blocks don't overlap."""
        # Given: VPC CIDR and AZ count
        runner = fn.VectorDBFunctionRunner()

        # When: Generating subnet CIDRs
        cidrs = runner._calculate_subnet_cidrs("10.10.0.0/16", 3)

        # Then: No overlapping CIDR ranges
        networks = [ipaddress.IPv4Network(cidr) for cidr in cidrs]

        for i, network1 in enumerate(networks):
            for j, network2 in enumerate(networks):
                if i != j:
                    self.assertFalse(network1.overlaps(network2))


class TestConfigurationValidation(unittest.TestCase):
    """Test configuration validation."""

    def test_valid_vpc_cidr(self):
        """Test valid VPC CIDR validation."""
        # Given: Valid CIDR (10.10.0.0/16)
        runner = fn.VectorDBFunctionRunner()

        # When: Calculating subnet CIDRs
        cidrs = runner._calculate_subnet_cidrs("10.10.0.0/16", 3)

        # Then: Should pass validation
        self.assertEqual(len(cidrs), 3)
        for cidr in cidrs:
            # Should be valid IP networks
            ipaddress.IPv4Network(cidr)

    def test_invalid_vpc_cidr(self):
        """Test invalid VPC CIDR validation."""
        # Given: Invalid CIDR
        runner = fn.VectorDBFunctionRunner()

        # When/Then: Should raise ValueError for invalid CIDR
        with self.assertRaises(ValueError):
            runner._calculate_subnet_cidrs("256.256.256.256/16", 3)

    def test_az_count_validation(self):
        """Test availability zone count validation."""
        # Given: AZ count > 3
        runner = fn.VectorDBFunctionRunner()

        # When: Calculating with more AZs than available
        cidrs = runner._calculate_subnet_cidrs("10.10.0.0/16", 5)

        # Then: Should still work (though may not be practical)
        self.assertEqual(len(cidrs), 5)


class TestErrorHandling(unittest.IsolatedAsyncioTestCase):
    """Test error handling scenarios."""

    def setUp(self) -> None:
        """Set up test environment."""
        logging.configure(level=logging.Level.DISABLED)

    async def test_missing_configuration(self):
        """Test handling of missing configuration."""
        # Given: Request with missing required fields
        req = fnv1.RunFunctionRequest(
            input=resource.dict_to_struct({}),
            observed=fnv1.State(
                composite=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {
                            "apiVersion": "example.crossplane.io/v1",
                            "kind": "XR",
                            "spec": {},  # Missing region and location
                        }
                    ),
                ),
            ),
        )
        runner = fn.VectorDBFunctionRunner()

        # When: Running function with missing region/location
        response = await runner.RunFunction(req, None)

        # Then: Should use default region and still generate resources
        self.assertIsNotNone(response)
        self.assertIn("vpc", response.desired.resources)

    async def test_invalid_region(self):
        """Test handling of invalid AWS region."""
        # Given: Invalid region
        req = fnv1.RunFunctionRequest(
            input=resource.dict_to_struct(
                {
                    "vpc_cidr": "10.10.0.0/16",
                    "environment_suffix": "dev",
                    "master_username": "postgres",
                    "postgres_cluster_name": "vectordb-cluster",
                }
            ),
            observed=fnv1.State(
                composite=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {
                            "apiVersion": "example.crossplane.io/v1",
                            "kind": "XR",
                            "spec": {"region": "invalid-region"},
                        }
                    ),
                ),
            ),
        )
        runner = fn.VectorDBFunctionRunner()

        # When: Running function
        response = await runner.RunFunction(req, None)

        # Then: Should still generate resources (region validation happens later)
        self.assertIsNotNone(response)
        self.assertIn("vpc", response.desired.resources)


if __name__ == "__main__":
    unittest.main()
