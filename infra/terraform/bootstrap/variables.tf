variable "aws_region" {
  type        = string
  description = "AWS region for state backend bootstrap"
  default     = "ap-south-1"
}

variable "project" {
  type        = string
  description = "Project name used in resource naming"
  default     = "sahulatkar"
}

variable "environment" {
  type        = string
  description = "Environment name for bootstrap resources"
  default     = "shared"
}

variable "state_bucket_name" {
  type        = string
  description = "Globally unique S3 bucket name for Terraform state"
}

variable "lock_table_name" {
  type        = string
  description = "DynamoDB table name for Terraform state locking"
  default     = "sk-terraform-locks"
}

variable "force_destroy_state_bucket" {
  type        = bool
  description = "Allow Terraform to destroy the state bucket"
  default     = false
}
