output "rds_key_arn" {
  description = "KMS key ARN used for RDS encryption"
  value       = aws_kms_key.keys["rds"].arn
}

output "s3_key_arn" {
  description = "KMS key ARN used for S3 encryption"
  value       = aws_kms_key.keys["s3"].arn
}

output "secrets_key_arn" {
  description = "KMS key ARN used for Secrets Manager encryption"
  value       = aws_kms_key.keys["secrets"].arn
}