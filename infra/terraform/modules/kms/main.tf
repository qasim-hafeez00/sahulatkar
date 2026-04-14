locals {
  key_specs = {
    rds     = "KMS key for RDS encryption"
    s3      = "KMS key for S3 bucket encryption"
    secrets = "KMS key for Secrets Manager encryption"
  }

  default_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_kms_key" "keys" {
  for_each = local.key_specs

  description             = "sk-${var.environment}-${each.key}: ${each.value}"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = merge(local.default_tags, var.tags, {
    Name = "sk-${var.environment}-${each.key}"
  })
}

resource "aws_kms_alias" "aliases" {
  for_each = aws_kms_key.keys

  name          = "alias/sk-${var.environment}-${each.key}"
  target_key_id = each.value.key_id
}