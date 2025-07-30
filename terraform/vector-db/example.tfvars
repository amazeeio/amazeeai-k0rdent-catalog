region = "eu-central-1"

environment_suffix = "prod"

postgres_cluster_name                = "amazeeai-vectordb"
postgres_cluster_min_capacity        = 0.5
postgres_cluster_max_capacity        = 16
postgres_cluster_backup_window       = "06:42-07:12"
postgres_cluster_maintenance_window  = "wed:04:35-wed:05:05"

tags = {
  Environment = "production"
  Project     = "amazeeai"
  Component   = "vectordb"
}