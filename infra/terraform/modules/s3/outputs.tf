output "bucket_names" {
  description = "Map of bucket names"
  value       = { for name, bucket in aws_s3_bucket.buckets : name => bucket.id }
}

output "bucket_arns" {
  description = "Map of bucket ARNs"
  value       = { for name, bucket in aws_s3_bucket.buckets : name => bucket.arn }
}