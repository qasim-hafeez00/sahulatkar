terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  common_tags = {
    Project     = "sahulatkar"
    Environment = var.environment
    ManagedBy   = "terraform"
  }

  bucket_definitions = {
    contracts = {
      versioning                  = true
      transition_to_ia_after_days = 365
      data_class                  = "confidential"
    }
    "kyc-images" = {
      versioning                  = true
      transition_to_ia_after_days = 365
      data_class                  = "sensitive"
    }
    screenshots = {
      versioning                  = true
      transition_to_ia_after_days = 90
      data_class                  = "internal"
    }
    static = {
      versioning = true
      data_class = "public"
    }
  }

  node_groups = {
    general = {
      instance_types = ["m6g.large"]
      min_size       = 3
      max_size       = 10
      desired_size   = 3
    }
    playwright = {
      instance_types = ["m6i.2xlarge"]
      min_size       = 0
      max_size       = 20
      desired_size   = 0
      taints = [
        {
          key    = "workload"
          value  = "playwright"
          effect = "NO_SCHEDULE"
        }
      ]
      labels = {
        workload = "playwright"
      }
    }
  }
}

module "vpc" {
  source = "../../modules/vpc"

  project                = "sahulatkar"
  environment            = var.environment
  vpc_cidr               = var.vpc_cidr
  azs                    = var.azs
  private_subnets        = var.private_subnets
  public_subnets         = var.public_subnets
  database_subnets       = var.database_subnets
  single_nat_gateway     = false
  one_nat_gateway_per_az = true
  tags                   = local.common_tags
}

module "kms" {
  source = "../../modules/kms"

  project     = "sahulatkar"
  environment = var.environment
  tags        = local.common_tags
}

module "eks" {
  source = "../../modules/eks"

  project                        = "sahulatkar"
  environment                    = var.environment
  vpc_id                         = module.vpc.vpc_id
  private_subnet_ids             = module.vpc.private_subnet_ids
  node_groups                    = local.node_groups
  cluster_endpoint_public_access = var.eks_public_endpoint
  tags                           = local.common_tags
}

module "iam" {
  source = "../../modules/iam"

  project           = "sahulatkar"
  environment       = var.environment
  enable_irsa_role  = false
  oidc_provider_arn = module.eks.oidc_provider_arn
  oidc_provider_url = module.eks.cluster_oidc_issuer_url
  tags              = local.common_tags
}

module "rds" {
  source = "../../modules/rds"

  project                     = "sahulatkar"
  environment                 = var.environment
  vpc_id                      = module.vpc.vpc_id
  allowed_cidr_blocks         = module.vpc.private_subnet_cidr_blocks
  db_subnet_group_name        = module.vpc.database_subnet_group_name
  instance_class              = "db.r6g.xlarge"
  allocated_storage           = 100
  max_allocated_storage       = 500
  multi_az                    = true
  backup_retention_period     = 35
  deletion_protection         = true
  create_read_replica         = var.create_read_replica
  read_replica_instance_class = "db.r6g.large"
  rds_kms_key_arn             = module.kms.rds_key_arn
  secrets_kms_key_arn         = module.kms.secrets_key_arn
  tags                        = local.common_tags
}

module "elasticache" {
  source = "../../modules/elasticache"

  project             = "sahulatkar"
  environment         = var.environment
  vpc_id              = module.vpc.vpc_id
  subnet_ids          = module.vpc.private_subnet_ids
  allowed_cidr_blocks = module.vpc.private_subnet_cidr_blocks
  node_type           = "cache.r6g.large"
  num_cache_clusters  = 3
  auth_token          = var.redis_auth_token
  tags                = local.common_tags
}

module "ecr" {
  source = "../../modules/ecr"

  project          = "sahulatkar"
  environment      = var.environment
  keep_last_images = 10
  tags             = local.common_tags
}

module "s3" {
  source = "../../modules/s3"

  project            = "sahulatkar"
  environment        = var.environment
  bucket_prefix      = "sk"
  bucket_definitions = local.bucket_definitions
  s3_kms_key_arn     = module.kms.s3_key_arn
  tags               = local.common_tags
}

module "pgbouncer" {
  source = "../../modules/pgbouncer"

  project                = "sahulatkar"
  environment            = var.environment
  aws_region             = var.aws_region
  vpc_id                 = module.vpc.vpc_id
  private_subnet_ids     = module.vpc.private_subnet_ids
  allowed_cidr_blocks    = module.vpc.private_subnet_cidr_blocks
  db_cidr_blocks         = module.vpc.database_subnet_cidr_blocks
  execution_role_arn     = module.iam.pgbouncer_execution_role_arn
  task_role_arn          = module.iam.pgbouncer_task_role_arn
  desired_count          = 2
  db_host                = module.rds.db_instance_endpoint
  db_name                = "sahulatkar"
  db_user                = "sk_admin"
  db_password_secret_arn = var.db_password_secret_arn
  tags                   = local.common_tags
}
