variable "project" {
  type        = string
  description = "Project label for tags"
  default     = "sahulatkar"
}

variable "environment" {
  type        = string
  description = "Environment name"
}

variable "tags" {
  type        = map(string)
  description = "Additional tags"
  default     = {}
}