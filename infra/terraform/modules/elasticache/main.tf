locals {
  default_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_security_group" "redis" {
  name        = "sk-${var.environment}-redis-sg"
  description = "Redis security group"
  vpc_id      = var.vpc_id

  ingress {
    description = "Redis from private subnets"
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.default_tags, var.tags)
}

resource "aws_elasticache_subnet_group" "redis" {
  name       = "sk-${var.environment}-redis-subnets"
  subnet_ids = var.subnet_ids
}

resource "aws_elasticache_parameter_group" "redis" {
  name   = "sk-${var.environment}-redis7"
  family = "redis7"

  parameter {
    name  = "maxmemory-policy"
    value = "allkeys-lru"
  }
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "sk-${var.environment}"
  description          = "Sahulatkar Redis cluster"

  engine               = "redis"
  engine_version       = var.engine_version
  node_type            = var.node_type
  num_cache_clusters   = var.num_cache_clusters
  parameter_group_name = aws_elasticache_parameter_group.redis.name

  subnet_group_name         = aws_elasticache_subnet_group.redis.name
  security_group_ids        = [aws_security_group.redis.id]
  port                      = 6379
  at_rest_encryption_enabled = true
  transit_encryption_enabled = var.auth_token != null
  auth_token                = var.auth_token
  automatic_failover_enabled = var.num_cache_clusters > 1

  tags = merge(local.default_tags, var.tags)
}