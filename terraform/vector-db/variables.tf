variable "region" {
  description = "AWS region for resources"
  type        = string
  default     = "eu-central-1"
}

variable "environment_suffix" {
  description = "Environment suffix for resource naming"
  type        = string
}

variable "postgres_cluster" {
  description = "PostgreSQL cluster configuration"
  type = object({
    name                = string
    min_capacity        = number
    max_capacity        = number
    backup_window       = string
    maintenance_window  = string
  })
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
}