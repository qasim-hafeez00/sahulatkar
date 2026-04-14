variable "project" {
  type        = string
  description = "Project label for tags"
  default     = "sahulatkar"
}

variable "environment" {
  type        = string
  description = "Environment name"
}

variable "bucket_prefix" {
  type        = string
  description = "Prefix for bucket names"
  default     = "sk"
}

variable "s3_kms_key_arn" {
  type        = string
  description = "KMS key ARN for S3 encryption"
}

variable "bucket_definitions" {
  type = map(object({
    versioning                  = bool
    transition_to_ia_after_days = optional(number)
    data_class                  = string
  }))
  description = "Bucket definitions"
}

variable "tags" {
  type        = map(string)
  description = "Additional tags"
  default     = {}
}