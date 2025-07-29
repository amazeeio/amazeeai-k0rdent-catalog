# VectorDB Outputs
output "vectordb_cluster_endpoints" {
  description = "Writer endpoints for each cluster"
  value       = module.aurora.cluster_endpoint
}

output "vectordb_cluster_reader_endpoints" {
  description = "Read-only endpoints for each cluster"
  value       = module.aurora.cluster_reader_endpoint
}

output "vectordb_cluster_ids" {
  description = "The IDs of each cluster"
  value       = module.aurora.cluster_id
}

output "vectordb_master_passwords" {
  description = "The master passwords for each database"
  value       = random_password.master_password.result
  sensitive   = true
}

output "vpc_id" {
  description = "The ID of the VPC"
  value       = module.vpc.vpc_id
}

output "database_subnet_group_name" {
  description = "The name of the database subnet group"
  value       = module.vpc.database_subnet_group_name
}