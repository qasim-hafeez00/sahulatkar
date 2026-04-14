output "pgbouncer_execution_role_arn" {
  description = "ECS task execution role ARN for PgBouncer"
  value       = aws_iam_role.pgbouncer_execution.arn
}

output "pgbouncer_task_role_arn" {
  description = "ECS task role ARN for PgBouncer"
  value       = aws_iam_role.pgbouncer_task.arn
}

output "irsa_role_arn" {
  description = "IRSA workload role ARN"
  value       = var.enable_irsa_role ? aws_iam_role.irsa_workload[0].arn : null
}