data "aws_caller_identity" "current" {}

locals {
  default_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_s3_bucket" "buckets" {
  for_each = var.bucket_definitions

  bucket = format(
    "%s-%s-%s-%s",
    var.bucket_prefix,
    var.environment,
    each.key,
    data.aws_caller_identity.current.account_id
  )

  tags = merge(local.default_tags, var.tags, {
    Name      = "sk-${var.environment}-${each.key}"
    DataClass = each.value.data_class
  })
}

resource "aws_s3_bucket_public_access_block" "buckets" {
  for_each = aws_s3_bucket.buckets

  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "buckets" {
  for_each = aws_s3_bucket.buckets

  bucket = each.value.id

  versioning_configuration {
    status = lookup(var.bucket_definitions[each.key], "versioning", false) ? "Enabled" : "Suspended"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "buckets" {
  for_each = aws_s3_bucket.buckets

  bucket = each.value.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.s3_kms_key_arn
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "buckets" {
  for_each = {
    for name, def in var.bucket_definitions :
    name => def
    if try(def.transition_to_ia_after_days, null) != null
  }

  bucket = aws_s3_bucket.buckets[each.key].id

  rule {
    id     = "transition-to-ia"
    status = "Enabled"

    transition {
      days          = each.value.transition_to_ia_after_days
      storage_class = "STANDARD_IA"
    }
  }
}