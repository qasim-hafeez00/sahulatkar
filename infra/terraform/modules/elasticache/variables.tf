variable "project" {
  type        = string
  description = "Project label for tags"
  default     = "sahulatkar"
}

variable "environment" {
  type        = string
  description = "Environment name"
}

variable "vpc_id" {
  type        = string
  description = "VPC ID"
}

variable "subnet_ids" {
  type        = list(string)
  description = "Subnet IDs for Redis"
}

variable "allowed_cidr_blocks" {
  type        = list(string)
  description = "CIDR blocks allowed to connect to Redis"
}

variable "node_type" {
  type        = string
  description = "ElastiCache node type"
}

variable "num_cache_clusters" {
  type        = number
  description = "Number of cache nodes"
  default     = 1
}

variable "engine_version" {
  type        = string
  description = "Redis engine version"
  default     = "7.1"
}

variable "auth_token" {
  type        = string
  description = "Redis auth token (required for transit encryption)"
  default     = null
  sensitive   = true
}

variable "tags" {
  type        = map(string)
  description = "Additional tags"
  default     = {}
}