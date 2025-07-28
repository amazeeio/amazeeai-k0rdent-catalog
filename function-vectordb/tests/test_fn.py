import dataclasses
import unittest

from crossplane.function import logging, resource
from crossplane.function.proto.v1 import run_function_pb2 as fnv1

from function.fn import FunctionRunner


class TestFunctionRunner(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        # Allow larger diffs, since we diff large strings of JSON.
        self.maxDiff = None

        logging.configure(level=logging.Level.DISABLED)

    async def test_run_function_basic(self) -> None:
        """
        Given a basic vector database request with minimal configuration
        When the function runs
        Then it should create all required infrastructure resources
        """

        @dataclasses.dataclass
        class TestCase:
            reason: str
            req: fnv1.RunFunctionRequest
            expected_resource_count: int

        cases = [
            TestCase(
                reason="Basic vector database infrastructure creation",
                req=fnv1.RunFunctionRequest(
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
                ),
                expected_resource_count=25,
                # VPC, IGW, 6 subnets, 2 route tables, 2 routes,
                # 4 route table associations, SG, IAM role, 2 parameter groups,
                # password, cluster, instance, secret
            ),
        ]

        runner = FunctionRunner()

        for case in cases:
            got = await runner.RunFunction(case.req, None)

            # Check that we get the expected number of resources
            self.assertEqual(
                len(got.desired.resources),
                case.expected_resource_count,
                f"Expected {case.expected_resource_count} resources, "
                f"got {len(got.desired.resources)}",
            )

            # Check that TTL is set
            self.assertEqual(got.meta.ttl.seconds, 60)

    async def test_run_function_with_custom_config(self) -> None:
        """
        Given a vector database request with custom configuration
        When the function runs
        Then it should create resources with the custom settings
        """
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

        # Check that resources are created with custom settings
        aurora_cluster = got.desired.resources["aurora-cluster"]
        cluster_spec = aurora_cluster.resource["spec"]["forProvider"]

        self.assertEqual(cluster_spec["engineVersion"], "16.7")
        self.assertEqual(cluster_spec["masterUsername"], "admin")
        self.assertEqual(cluster_spec["backupRetentionPeriod"], 14)
        self.assertEqual(cluster_spec["preferredBackupWindow"], "03:00-03:30")
        self.assertEqual(
            cluster_spec["preferredMaintenanceWindow"], "sun:02:00-sun:03:00"
        )
        self.assertEqual(cluster_spec["deletionProtection"], False)

        aurora_instance = got.desired.resources["aurora-instance"]
        instance_spec = aurora_instance.resource["spec"]["forProvider"]
        scaling_config = instance_spec["serverlessV2ScalingConfiguration"]

        self.assertEqual(scaling_config["minCapacity"], 4)
        self.assertEqual(scaling_config["maxCapacity"], 32)

        # Check that password generation is disabled
        self.assertNotIn("random-password", got.desired.resources)

    async def test_availability_zone_mapping(self) -> None:
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
            got = await runner.RunFunction(req, None)

            # Check that subnets use correct AZ mapping
            for i in range(1, 3):
                public_subnet = got.desired.resources[f"public-subnet-{i}"]
                private_subnet = got.desired.resources[f"private-subnet-{i}"]
                database_subnet = got.desired.resources[f"database-subnet-{i}"]

                az_suffix = "a" if i == 1 else "b"
                expected_az = f"{region}{az_suffix}"

                self.assertEqual(
                    public_subnet.resource["spec"]["forProvider"]["availabilityZone"],
                    expected_az,
                )
                self.assertEqual(
                    private_subnet.resource["spec"]["forProvider"]["availabilityZone"],
                    expected_az,
                )
                self.assertEqual(
                    database_subnet.resource["spec"]["forProvider"]["availabilityZone"],
                    expected_az,
                )

    async def test_default_values(self) -> None:
        """
        Given a vector database request with minimal spec
        When the function runs
        Then it should use default values for optional parameters
        """
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

        # Check default values
        aurora_cluster = got.desired.resources["aurora-cluster"]
        cluster_spec = aurora_cluster.resource["spec"]["forProvider"]

        self.assertEqual(cluster_spec["engineVersion"], "16.6")
        self.assertEqual(cluster_spec["masterUsername"], "postgres")
        self.assertEqual(cluster_spec["backupRetentionPeriod"], 7)
        self.assertEqual(cluster_spec["preferredBackupWindow"], "06:42-07:12")
        self.assertEqual(
            cluster_spec["preferredMaintenanceWindow"], "wed:04:35-wed:05:05"
        )
        self.assertEqual(cluster_spec["deletionProtection"], True)

        aurora_instance = got.desired.resources["aurora-instance"]
        instance_spec = aurora_instance.resource["spec"]["forProvider"]
        scaling_config = instance_spec["serverlessV2ScalingConfiguration"]

        self.assertEqual(scaling_config["minCapacity"], 2)
        self.assertEqual(scaling_config["maxCapacity"], 16)

        # Check that password generation is enabled by default
        self.assertIn("random-password", got.desired.resources)

        # Check default database name
        db_secret = got.desired.resources["db-secret"]
        self.assertEqual(db_secret.resource["stringData"]["database"], "vectordb")

    async def test_resource_structure(self) -> None:
        """
        Given a vector database request
        When the function runs
        Then all resources should have the correct structure and metadata
        """
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

        # Check that all resources have proper metadata and provider config
        for _resource_name, resource_obj in got.desired.resources.items():
            # All resources should have annotations
            self.assertIn("metadata", resource_obj.resource)
            self.assertIn("annotations", resource_obj.resource["metadata"])
            self.assertIn(
                "crossplane.io/external-name",
                resource_obj.resource["metadata"]["annotations"],
            )

            # All AWS resources should have provider config
            if resource_obj.resource["apiVersion"] != "v1":  # Skip Kubernetes Secret
                self.assertIn("spec", resource_obj.resource)
                self.assertIn("providerConfigRef", resource_obj.resource["spec"])
                self.assertEqual(
                    resource_obj.resource["spec"]["providerConfigRef"]["name"],
                    "creds-provider",
                )

        # Check specific resource types
        self.assertEqual(
            got.desired.resources["vpc"].resource["apiVersion"],
            "vpc.aws.upbound.io/v1beta1",
        )
        self.assertEqual(got.desired.resources["vpc"].resource["kind"], "VPC")

        self.assertEqual(
            got.desired.resources["aurora-cluster"].resource["apiVersion"],
            "rds.aws.upbound.io/v1beta1",
        )
        self.assertEqual(
            got.desired.resources["aurora-cluster"].resource["kind"], "Cluster"
        )

        self.assertEqual(
            got.desired.resources["aurora-instance"].resource["apiVersion"],
            "rds.aws.upbound.io/v1beta1",
        )
        self.assertEqual(
            got.desired.resources["aurora-instance"].resource["kind"], "Instance"
        )


if __name__ == "__main__":
    unittest.main()
