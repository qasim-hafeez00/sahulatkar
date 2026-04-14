locals {
  default_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_ecs_cluster" "this" {
  name = "sk-${var.environment}-pgbouncer"

  tags = merge(local.default_tags, var.tags)
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/ecs/sk-${var.environment}-pgbouncer"
  retention_in_days = 14

  tags = merge(local.default_tags, var.tags)
}

resource "aws_security_group" "pgbouncer" {
  name        = "sk-${var.environment}-pgbouncer-sg"
  description = "PgBouncer security group"
  vpc_id      = var.vpc_id

  ingress {
    description = "PgBouncer port"
    from_port   = 6432
    to_port     = 6432
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  egress {
    description = "PostgreSQL outbound"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = var.db_cidr_blocks
  }

  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.default_tags, var.tags)
}

resource "aws_ecs_task_definition" "this" {
  family                   = "sk-${var.environment}-pgbouncer"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = tostring(var.task_cpu)
  memory                   = tostring(var.task_memory)
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.task_role_arn

  container_definitions = jsonencode([
    {
      name      = "pgbouncer"
      image     = var.image
      essential = true
      portMappings = [
        {
          containerPort = 6432
          hostPort      = 6432
          protocol      = "tcp"
        }
      ]
      environment = [
        { name = "DB_HOST", value = var.db_host },
        { name = "DB_PORT", value = tostring(var.db_port) },
        { name = "DB_NAME", value = var.db_name },
        { name = "DB_USER", value = var.db_user }
      ]
      secrets = var.db_password_secret_arn == "" ? [] : [
        {
          name      = "DB_PASSWORD"
          valueFrom = var.db_password_secret_arn
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.this.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "ecs"
        }
      }
    }
  ])

  tags = merge(local.default_tags, var.tags)
}

resource "aws_ecs_service" "this" {
  name            = "sk-${var.environment}-pgbouncer"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.this.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.pgbouncer.id]
    assign_public_ip = false
  }

  tags = merge(local.default_tags, var.tags)
}