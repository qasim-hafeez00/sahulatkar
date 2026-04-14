variable "project" {
  type        = string
  description = "Project label for tags"
  default     = "sahulatkar"
}

variable "environment" {
  type        = string
  description = "Environment name"
}

variable "kubernetes_version" {
  type        = string
  description = "EKS Kubernetes version"
  default     = "1.29"
}

variable "vpc_id" {
  type        = string
  description = "VPC ID"
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs for EKS nodes and control plane"
}

variable "cluster_endpoint_public_access" {
  type        = bool
  description = "Expose cluster endpoint publicly"
  default     = true
}

variable "node_groups" {
  type        = any
  description = "Managed node group map"
}

variable "tags" {
  type        = map(string)
  description = "Additional tags"
  default     = {}
}