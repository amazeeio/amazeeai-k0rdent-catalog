variable "region" {
  description = "AWS region for resources"
  type        = string
  default     = "eu-central-1"
}

variable "environment_suffix" {
  description = "Environment suffix for resource naming"
  type        = string
}

variable "postgres_cluster_name" {
  description = "PostgreSQL cluster name"
  type        = string
}

variable "postgres_cluster_min_capacity" {
  description = "PostgreSQL cluster minimum capacity"
  type        = number
}

variable "postgres_cluster_max_capacity" {
  description = "PostgreSQL cluster maximum capacity"
  type        = number
}

variable "postgres_cluster_backup_window" {
  description = "PostgreSQL cluster backup window"
  type        = string
}

variable "postgres_cluster_maintenance_window" {
  description = "PostgreSQL cluster maintenance window"
  type        = string
}

variable "engine_version" {
  description = "Aurora PostgreSQL engine version"
  type        = string
  default     = "16.6"
}

variable "master_username" {
  description = "Master database username"
  type        = string
  default     = "postgres"
}

variable "backup_retention_period" {
  description = "Days to retain backups"
  type        = number
  default     = 7
}

variable "deletion_protection" {
  description = "Enable deletion protection"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
}