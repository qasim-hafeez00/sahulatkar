variable "aws_region" {
  type        = string
  description = "AWS region"
  default     = "ap-south-1"
}

variable "environment" {
  type        = string
  description = "Environment name"
  default     = "production"
}

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR"
  default     = "10.20.0.0/16"
}

variable "azs" {
  type        = list(string)
  description = "Availability zones"
  default     = ["ap-south-1a", "ap-south-1b"]
}

variable "private_subnets" {
  type        = list(string)
  description = "Private subnet CIDRs"
  default     = ["10.20.1.0/24", "10.20.2.0/24"]
}

variable "public_subnets" {
  type        = list(string)
  description = "Public subnet CIDRs"
  default     = ["10.20.101.0/24", "10.20.102.0/24"]
}

variable "database_subnets" {
  type        = list(string)
  description = "Database subnet CIDRs"
  default     = ["10.20.201.0/24", "10.20.202.0/24"]
}

variable "eks_public_endpoint" {
  type        = bool
  description = "Whether EKS API endpoint is publicly reachable"
  default     = false
}

variable "redis_auth_token" {
  type        = string
  description = "Redis auth token for transit encryption"
  sensitive   = true
}

variable "db_password_secret_arn" {
  type        = string
  description = "Secrets Manager ARN containing DB password for PgBouncer"
}

variable "create_read_replica" {
  type        = bool
  description = "Create production read replica"
  default     = true
}
