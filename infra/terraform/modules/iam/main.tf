data "aws_iam_policy_document" "ecs_tasks_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

locals {
  default_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_iam_role" "pgbouncer_execution" {
  name               = "sk-${var.environment}-pgbouncer-exec-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json

  tags = merge(local.default_tags, var.tags)
}

resource "aws_iam_role_policy_attachment" "pgbouncer_execution_policy" {
  role       = aws_iam_role.pgbouncer_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "pgbouncer_task" {
  name               = "sk-${var.environment}-pgbouncer-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json

  tags = merge(local.default_tags, var.tags)
}

resource "aws_iam_role_policy" "pgbouncer_task_inline" {
  name = "sk-${var.environment}-pgbouncer-task-policy"
  role = aws_iam_role.pgbouncer_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "kms:Decrypt"
        ]
        Resource = "*"
      }
    ]
  })
}

data "aws_iam_policy_document" "irsa_assume_role" {
  count = var.enable_irsa_role ? 1 : 0

  statement {
    effect = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(var.oidc_provider_url, "https://", "")}:sub"
      values   = ["system:serviceaccount:${var.irsa_namespace}:${var.irsa_service_account}"]
    }
  }
}

resource "aws_iam_role" "irsa_workload" {
  count = var.enable_irsa_role ? 1 : 0

  name               = "sk-${var.environment}-${var.irsa_role_name}"
  assume_role_policy = data.aws_iam_policy_document.irsa_assume_role[0].json

  tags = merge(local.default_tags, var.tags)
}

resource "aws_iam_role_policy" "irsa_workload_inline" {
  count = var.enable_irsa_role && var.irsa_policy_json != "" ? 1 : 0

  name   = "sk-${var.environment}-${var.irsa_role_name}-policy"
  role   = aws_iam_role.irsa_workload[0].id
  policy = var.irsa_policy_json
}