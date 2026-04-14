output "vpc_id" {
  description = "Staging VPC ID"
  value       = module.vpc.vpc_id
}

output "eks_cluster_name" {
  description = "Staging EKS cluster name"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "Staging EKS cluster endpoint"
  value       = module.eks.cluster_endpoint
}

output "rds_key_arn" {
  description = "Staging KMS key ARN for RDS"
  value       = module.kms.rds_key_arn
}

output "s3_key_arn" {
  description = "Staging KMS key ARN for S3"
  value       = module.kms.s3_key_arn
}

output "secrets_key_arn" {
  description = "Staging KMS key ARN for Secrets Manager"
  value       = module.kms.secrets_key_arn
}

output "rds_endpoint" {
  description = "Staging RDS endpoint"
  value       = module.rds.db_instance_endpoint
}

output "redis_primary_endpoint" {
  description = "Staging Redis primary endpoint"
  value       = module.elasticache.primary_endpoint
}

output "ecr_repository_urls" {
  description = "Staging ECR repository URLs"
  value       = module.ecr.repository_urls
}

output "s3_bucket_names" {
  description = "Staging S3 bucket names"
  value       = module.s3.bucket_names
}

output "pgbouncer_service_name" {
  description = "Staging PgBouncer ECS service name"
  value       = module.pgbouncer.service_name
}