terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
      configuration_aliases = [aws]
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

# Configure the AWS Provider
provider "aws" {
  alias  = "main"
  region = var.region
}

# Data sources
data "aws_availability_zones" "available" {
  provider = aws.main
}

# VPC Module
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  providers = {
    aws = aws.main
  }

  name = "amazeeai-vectordb-vpc-${var.environment_suffix}"
  cidr = "10.10.0.0/16"
  azs  = slice(data.aws_availability_zones.available.names, 0, 3)

  # Define subnets based on these AZs and the VPC CIDR
  public_subnets   = [for k, az_name in slice(data.aws_availability_zones.available.names, 0, 3) : cidrsubnet("10.10.0.0/16", 8, k)]
  private_subnets  = [for k, az_name in slice(data.aws_availability_zones.available.names, 0, 3) : cidrsubnet("10.10.0.0/16", 8, k + 3)]
  database_subnets = [for k, az_name in slice(data.aws_availability_zones.available.names, 0, 3) : cidrsubnet("10.10.0.0/16", 8, k + 6)]

  create_database_subnet_route_table     = true
  create_database_internet_gateway_route = true

  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = var.tags
}

# Generate master password
resource "random_password" "master_password" {
  length           = 16
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

# Aurora PostgreSQL Cluster
module "aurora" {
  source  = "terraform-aws-modules/rds-aurora/aws"
  version = "~> 9.0"

  providers = {
    aws = aws.main
  }

  engine         = "aurora-postgresql"
  engine_version = "16.6"
  engine_mode    = "provisioned"

  availability_zones = slice(data.aws_availability_zones.available.names, 0, 3)

  storage_encrypted   = true
  master_username     = "postgres"
  master_password     = random_password.master_password.result

  manage_master_user_password          = false
  manage_master_user_password_rotation = false

  vpc_id               = module.vpc.vpc_id
  db_subnet_group_name = module.vpc.database_subnet_group_name

  security_group_rules = {
    vpc_ingress = {
      cidr_blocks = ["0.0.0.0/0"]
    }
  }

  name = var.postgres_cluster.name

  instances = {
    instance1 = {
      instance_class      = "db.serverless"
      publicly_accessible = true
    }
    instance2 = {
      instance_class      = "db.serverless"
      publicly_accessible = true
    }
  }

  serverlessv2_scaling_configuration = {
    min_capacity = var.postgres_cluster.min_capacity
    max_capacity = var.postgres_cluster.max_capacity
  }

  preferred_backup_window      = var.postgres_cluster.backup_window
  preferred_maintenance_window = var.postgres_cluster.maintenance_window

  backup_retention_period = 7

  monitoring_interval    = 60
  create_monitoring_role = true

  performance_insights_enabled          = true
  performance_insights_retention_period = 7

  db_cluster_parameter_group_name    = "default.aurora-postgresql16"
  create_db_cluster_parameter_group  = false
  db_parameter_group_name           = "default.aurora-postgresql16"
  create_db_parameter_group         = false

  copy_tags_to_snapshot               = true
  deletion_protection                 = true
  iam_database_authentication_enabled = false
  network_type                        = "IPV4"
  enable_http_endpoint                = false
  auto_minor_version_upgrade          = true

  tags = var.tags
}