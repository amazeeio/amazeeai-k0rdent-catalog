terraform {
  required_version = ">= 1.5"

  backend "kubernetes" {
    secret_suffix = "vector-db"
    namespace     = "crossplane-system"
    in_cluster_config = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.6"
      configuration_aliases = [aws]
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}