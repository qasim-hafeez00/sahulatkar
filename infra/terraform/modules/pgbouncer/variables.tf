variable "project" {
  type        = string
  description = "Project label for tags"
  default     = "sahulatkar"
}

variable "environment" {
  type        = string
  description = "Environment name"
}

variable "aws_region" {
  type        = string
  description = "AWS region"
  default     = "ap-south-1"
}

variable "vpc_id" {
  type        = string
  description = "VPC ID"
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs for service networking"
}

variable "allowed_cidr_blocks" {
  type        = list(string)
  description = "CIDR blocks allowed to access PgBouncer"
}

variable "db_cidr_blocks" {
  type        = list(string)
  description = "CIDR blocks for database egress"
}

variable "execution_role_arn" {
  type        = string
  description = "ECS task execution role ARN"
}

variable "task_role_arn" {
  type        = string
  description = "ECS task role ARN"
}

variable "image" {
  type        = string
  description = "PgBouncer container image"
  default     = "edoburu/pgbouncer:1.21.0-p0"
}

variable "task_cpu" {
  type        = number
  description = "Task CPU units"
  default     = 512
}

variable "task_memory" {
  type        = number
  description = "Task memory in MiB"
  default     = 1024
}

variable "desired_count" {
  type        = number
  description = "Desired number of PgBouncer tasks"
  default     = 1
}

variable "db_host" {
  type        = string
  description = "Database host endpoint"
}

variable "db_port" {
  type        = number
  description = "Database port"
  default     = 5432
}

variable "db_name" {
  type        = string
  description = "Database name"
  default     = "sahulatkar"
}

variable "db_user" {
  type        = string
  description = "Database user"
  default     = "sk_admin"
}

variable "db_password_secret_arn" {
  type        = string
  description = "Secrets Manager ARN for DB password"
  default     = ""
}

variable "tags" {
  type        = map(string)
  description = "Additional tags"
  default     = {}
}