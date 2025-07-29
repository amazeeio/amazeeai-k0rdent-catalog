region = "eu-central-1"

environment_suffix = "prod"

postgres_cluster = {
  name                = "amazeeai-vectordb"
  min_capacity        = 0.5
  max_capacity        = 16
  backup_window       = "06:42-07:12"
  maintenance_window  = "wed:04:35-wed:05:05"
}

tags = {
  Environment = "production"
  Project     = "amazeeai"
  Component   = "vectordb"
}