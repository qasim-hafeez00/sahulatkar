output "cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "EKS cluster endpoint"
  value       = module.eks.cluster_endpoint
}

output "cluster_security_group_id" {
  description = "EKS cluster security group ID"
  value       = module.eks.cluster_security_group_id
}

output "oidc_provider_arn" {
  description = "OIDC provider ARN"
  value       = try(module.eks.oidc_provider_arn, null)
}

output "cluster_oidc_issuer_url" {
  description = "OIDC issuer URL"
  value       = try(module.eks.cluster_oidc_issuer_url, null)
}