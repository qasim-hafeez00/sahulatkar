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

variable "allowed_cidr_blocks" {
  type        = list(string)
  description = "CIDR blocks allowed to connect to RDS"
}

variable "db_subnet_group_name" {
  type        = string
  description = "Database subnet group name"
}

variable "engine_version" {
  type        = string
  description = "PostgreSQL engine version"
  default     = "16.2"
}

variable "instance_class" {
  type        = string
  description = "RDS instance class"
}

variable "allocated_storage" {
  type        = number
  description = "Allocated storage in GB"
}

variable "max_allocated_storage" {
  type        = number
  description = "Maximum allocated storage in GB"
}

variable "db_name" {
  type        = string
  description = "Database name"
  default     = "sahulatkar"
}

variable "db_username" {
  type        = string
  description = "Master username"
  default     = "sk_admin"
}

variable "multi_az" {
  type        = bool
  description = "Enable multi-AZ deployment"
  default     = false
}

variable "backup_retention_period" {
  type        = number
  description = "Backup retention days"
  default     = 7
}

variable "deletion_protection" {
  type        = bool
  description = "Enable deletion protection"
  default     = false
}

variable "create_read_replica" {
  type        = bool
  description = "Create a read replica"
  default     = false
}

variable "read_replica_instance_class" {
  type        = string
  description = "Read replica instance class"
  default     = "db.r6g.large"
}

variable "rds_kms_key_arn" {
  type        = string
  description = "KMS key ARN for RDS encryption"
}

variable "secrets_kms_key_arn" {
  type        = string
  description = "KMS key ARN for secrets encryption"
}

variable "tags" {
  type        = map(string)
  description = "Additional tags"
  default     = {}
}