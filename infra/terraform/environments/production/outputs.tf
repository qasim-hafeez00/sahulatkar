output "vpc_id" {
  description = "Production VPC ID"
  value       = module.vpc.vpc_id
}

output "eks_cluster_name" {
  description = "Production EKS cluster name"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "Production EKS cluster endpoint"
  value       = module.eks.cluster_endpoint
}

output "rds_key_arn" {
  description = "Production KMS key ARN for RDS"
  value       = module.kms.rds_key_arn
}

output "s3_key_arn" {
  description = "Production KMS key ARN for S3"
  value       = module.kms.s3_key_arn
}

output "secrets_key_arn" {
  description = "Production KMS key ARN for Secrets Manager"
  value       = module.kms.secrets_key_arn
}

output "rds_endpoint" {
  description = "Production RDS endpoint"
  value       = module.rds.db_instance_endpoint
}

output "rds_read_replica_endpoint" {
  description = "Production RDS read replica endpoint"
  value       = module.rds.read_replica_endpoint
}

output "redis_primary_endpoint" {
  description = "Production Redis primary endpoint"
  value       = module.elasticache.primary_endpoint
}

output "ecr_repository_urls" {
  description = "Production ECR repository URLs"
  value       = module.ecr.repository_urls
}

output "s3_bucket_names" {
  description = "Production S3 bucket names"
  value       = module.s3.bucket_names
}

output "pgbouncer_service_name" {
  description = "Production PgBouncer ECS service name"
  value       = module.pgbouncer.service_name
}

output "route53_zone_id" {
  description = "Route53 hosted zone ID for sahulatkar.com (looked up, not created - see infra/terraform/modules/dns)"
  value       = module.dns.zone_id
}

output "route53_name_servers" {
  description = "Authoritative name servers for the sahulatkar.com zone - confirm these match the domain registrar's NS records"
  value       = module.dns.name_servers
}

output "cert_manager_irsa_role_arn" {
  description = "IRSA role ARN for cert-manager's Route53 DNS-01 solver - annotate the cert-manager ServiceAccount with eks.amazonaws.com/role-arn set to this value at Helm install time"
  value       = module.cert_manager_irsa.irsa_role_arn
}

output "secrets_manager_irsa_role_arns" {
  description = "Per-service IRSA role ARNs for AWS Secrets Manager access (docs/SECRETS_MANAGER_MIGRATION.md), keyed by service name (gateway, product-service, payment-orchestrator, ledger-service, notification-service). Annotate each service's ServiceAccount (sk-<service> in infra/k8s/base/serviceaccounts.yaml) with eks.amazonaws.com/role-arn set to the matching value here."
  value       = { for service, mod in module.secrets_manager_irsa : service => mod.irsa_role_arn }
}