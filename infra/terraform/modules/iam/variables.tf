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

variable "enable_irsa_role" {
  type        = bool
  description = "Create a sample IRSA role"
  default     = false
}

variable "oidc_provider_arn" {
  type        = string
  description = "OIDC provider ARN from EKS"
  default     = ""
}

variable "oidc_provider_url" {
  type        = string
  description = "OIDC provider URL from EKS"
  default     = ""
}

variable "irsa_namespace" {
  type        = string
  description = "Kubernetes namespace for IRSA principal"
  default     = "default"
}

variable "irsa_service_account" {
  type        = string
  description = "Kubernetes service account for IRSA principal"
  default     = "default"
}

variable "irsa_role_name" {
  type        = string
  description = "Suffix for IRSA role name"
  default     = "workload-role"
}

variable "irsa_policy_json" {
  type        = string
  description = "Optional inline IAM policy document (JSON) to attach to the IRSA role. Ignored if enable_irsa_role is false or this is left empty."
  default     = ""
}