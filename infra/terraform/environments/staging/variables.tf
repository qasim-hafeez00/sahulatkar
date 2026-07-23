variable "aws_region" {
  type        = string
  description = "AWS region"
  default     = "ap-south-1"
}

variable "environment" {
  type        = string
  description = "Environment name"
  default     = "staging"
}

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR"
  default     = "10.10.0.0/16"
}

variable "azs" {
  type        = list(string)
  description = "Availability zones"
  default     = ["ap-south-1a", "ap-south-1b"]
}

variable "private_subnets" {
  type        = list(string)
  description = "Private subnet CIDRs"
  default     = ["10.10.1.0/24", "10.10.2.0/24"]
}

variable "public_subnets" {
  type        = list(string)
  description = "Public subnet CIDRs"
  default     = ["10.10.101.0/24", "10.10.102.0/24"]
}

variable "database_subnets" {
  type        = list(string)
  description = "Database subnet CIDRs"
  default     = ["10.10.201.0/24", "10.10.202.0/24"]
}

variable "eks_public_endpoint" {
  type        = bool
  description = "Whether EKS API endpoint is publicly reachable"
  default     = true
}

variable "redis_auth_token" {
  type        = string
  description = "Redis auth token for transit encryption"
  sensitive   = true
  default     = null
}

variable "db_password_secret_arn" {
  type        = string
  description = "Secrets Manager ARN containing DB password for PgBouncer"
  default     = ""
}

variable "root_domain_name" {
  type        = string
  description = "Apex domain name whose Route53 hosted zone is used for ingress TLS (cert-manager DNS-01). Assumes the zone already exists / is delegated - see infra/terraform/modules/dns."
  default     = "sahulatkar.com"
}
