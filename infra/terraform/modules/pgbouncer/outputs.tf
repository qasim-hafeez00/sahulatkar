output "cluster_name" {
  description = "PgBouncer ECS cluster name"
  value       = aws_ecs_cluster.this.name
}

output "service_name" {
  description = "PgBouncer ECS service name"
  value       = aws_ecs_service.this.name
}

output "security_group_id" {
  description = "PgBouncer security group ID"
  value       = aws_security_group.pgbouncer.id
}