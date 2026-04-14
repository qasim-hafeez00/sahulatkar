variable "project" {
  type        = string
  description = "Project label for tags"
  default     = "sahulatkar"
}

variable "environment" {
  type        = string
  description = "Environment name"
}

variable "repositories" {
  type        = list(string)
  description = "List of service repositories to create"
  default = [
    "gateway",
    "product-service",
    "credit-engine",
    "payment-orchestrator",
    "ledger-service",
    "notification-service",
    "web-customer",
    "web-admin"
  ]
}

variable "keep_last_images" {
  type        = number
  description = "How many images to keep in ECR"
  default     = 10
}

variable "tags" {
  type        = map(string)
  description = "Additional tags"
  default     = {}
}