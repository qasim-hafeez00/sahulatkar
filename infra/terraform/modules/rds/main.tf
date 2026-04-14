locals {
  default_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_security_group" "rds" {
  name        = "sk-${var.environment}-rds-sg"
  description = "RDS security group"
  vpc_id      = var.vpc_id

  ingress {
    description = "PostgreSQL from private subnets"
    from_port   = 5432
    to_port     = 5432
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

module "rds" {
  source  = "terraform-aws-modules/rds/aws"
  version = "~> 6.8"

  identifier = "sk-${var.environment}"

  engine               = "postgres"
  engine_version       = var.engine_version
  family               = "postgres16"
  major_engine_version = "16"
  instance_class       = var.instance_class

  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.max_allocated_storage

  db_name                             = var.db_name
  username                            = var.db_username
  port                                = 5432
  manage_master_user_password         = true
  master_user_secret_kms_key_id       = var.secrets_kms_key_arn
  db_subnet_group_name                = var.db_subnet_group_name
  vpc_security_group_ids              = [aws_security_group.rds.id]
  multi_az                            = var.multi_az
  backup_retention_period             = var.backup_retention_period
  deletion_protection                 = var.deletion_protection
  performance_insights_enabled        = true
  performance_insights_kms_key_id     = var.rds_kms_key_arn
  storage_encrypted                   = true
  kms_key_id                          = var.rds_kms_key_arn
  create_db_option_group              = false
  create_db_parameter_group           = true
  parameter_group_name                = "sk-${var.environment}-postgres16"
  parameter_group_use_name_prefix     = false
  enabled_cloudwatch_logs_exports     = ["postgresql"]

  parameters = [
    {
      name  = "shared_preload_libraries"
      value = "pg_stat_statements"
    },
    {
      name  = "log_min_duration_statement"
      value = "1000"
    }
  ]

  tags = merge(local.default_tags, var.tags)
}

resource "aws_db_instance" "read_replica" {
  count = var.create_read_replica ? 1 : 0

  identifier                    = "sk-${var.environment}-read"
  replicate_source_db           = module.rds.db_instance_identifier
  instance_class                = var.read_replica_instance_class
  storage_encrypted             = true
  kms_key_id                    = var.rds_kms_key_arn
  auto_minor_version_upgrade    = true
  publicly_accessible           = false
  copy_tags_to_snapshot         = true
  performance_insights_enabled  = true
  performance_insights_kms_key_id = var.rds_kms_key_arn

  tags = merge(local.default_tags, var.tags)
}