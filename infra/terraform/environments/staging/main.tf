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
      versioning                  = false
      transition_to_ia_after_days = 90
      data_class                  = "internal"
    }
    static = {
      versioning = false
      data_class = "public"
    }
  }

  node_groups = {
    general = {
      instance_types = ["t3.medium"]
      min_size       = 1
      max_size       = 3
      desired_size   = 2
    }
    playwright = {
      instance_types = ["m6i.2xlarge"]
      min_size       = 0
      max_size       = 2
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

  project                 = "sahulatkar"
  environment             = var.environment
  vpc_cidr                = var.vpc_cidr
  azs                     = var.azs
  private_subnets         = var.private_subnets
  public_subnets          = var.public_subnets
  database_subnets        = var.database_subnets
  single_nat_gateway      = true
  one_nat_gateway_per_az  = false
  tags                    = local.common_tags
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

# AWS Secrets Manager migration (docs/SECRETS_MANAGER_MIGRATION.md): one IRSA
# role per backend service, each scoped to only that service's own Secrets
# Manager namespace -- gateway's role can read "gateway/prod/*" and
# "gateway/staging/*" but nothing under "ledger-service/*", etc. credit-engine,
# web-admin, and web-customer are intentionally excluded (this pattern is for
# the 5 backend Python services with pydantic-settings Settings classes that
# call sk_shared.secrets_manager.load_secrets_manager_overrides -- see each
# service's src/config.py).
data "aws_caller_identity" "current" {}

locals {
  secrets_manager_services = [
    "gateway",
    "product-service",
    "payment-orchestrator",
    "ledger-service",
    "notification-service",
  ]
}

data "aws_iam_policy_document" "secrets_manager_read" {
  for_each = toset(local.secrets_manager_services)

  statement {
    sid    = "SecretsManagerRead"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]
    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${each.key}/prod/*",
      "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${each.key}/staging/*",
    ]
  }
}

# NOTE: Terraform only creates the role/trust policy, exactly like
# module.cert_manager_irsa below -- it does not modify
# infra/k8s/base/serviceaccounts.yaml (which must stay account-ID-free to
# avoid hardcoding AWS account IDs/ARNs in a checked-in manifest). Bind each
# role by annotating the matching ServiceAccount at deploy time, e.g.:
#   kubectl annotate serviceaccount sk-gateway -n sk-staging \
#     eks.amazonaws.com/role-arn=<secrets_manager_irsa_role_arns["gateway"] output> --overwrite
module "secrets_manager_irsa" {
  source   = "../../modules/iam"
  for_each = toset(local.secrets_manager_services)

  project              = "sahulatkar"
  environment          = var.environment
  enable_irsa_role     = true
  irsa_role_name       = "${each.key}-secrets-manager"
  irsa_namespace       = "sk-${var.environment}"
  irsa_service_account = "sk-${each.key}"
  irsa_policy_json     = data.aws_iam_policy_document.secrets_manager_read[each.key].json
  oidc_provider_arn    = module.eks.oidc_provider_arn
  oidc_provider_url    = module.eks.cluster_oidc_issuer_url
  tags                 = local.common_tags
}

# Looks up the pre-existing public Route53 hosted zone for sahulatkar.com.
# See infra/terraform/modules/dns/main.tf for the "zone already exists"
# assumption this relies on.
module "dns" {
  source = "../../modules/dns"

  domain_name = var.root_domain_name
}

# Least-privilege policy for cert-manager's Route53 DNS-01 solver, scoped to
# only the sahulatkar.com hosted zone (not "*" hosted zones in the account).
data "aws_iam_policy_document" "cert_manager_route53" {
  statement {
    sid    = "CertManagerRoute53ChangeRecords"
    effect = "Allow"
    actions = [
      "route53:ChangeResourceRecordSets",
      "route53:ListResourceRecordSets",
    ]
    resources = [module.dns.zone_arn]
  }

  statement {
    sid    = "CertManagerRoute53GetChange"
    effect = "Allow"
    actions = [
      "route53:GetChange",
    ]
    resources = ["arn:aws:route53:::change/*"]
  }

  statement {
    sid    = "CertManagerRoute53ListZones"
    effect = "Allow"
    actions = [
      "route53:ListHostedZonesByName",
    ]
    resources = ["*"]
  }
}

# IRSA role assumed by the cert-manager ServiceAccount (namespace
# "cert-manager", ServiceAccount "cert-manager" - the defaults used by the
# jetstack/cert-manager Helm chart) so it can complete ACME DNS-01 challenges
# against the sahulatkar.com Route53 zone without static AWS credentials.
#
# NOTE: the cert-manager Helm chart must be installed with
#   --set serviceAccount.annotations."eks\.amazonaws\.com/role-arn"=<cert_manager_irsa_role_arn output>
# for this role to actually be assumed - Terraform only creates the role/trust
# policy, it does not install cert-manager itself (see repo runbook for the
# manual `helm install` bootstrap steps, consistent with how ingress-nginx and
# other cluster add-ons are installed today).
module "cert_manager_irsa" {
  source = "../../modules/iam"

  project               = "sahulatkar"
  environment           = var.environment
  enable_irsa_role      = true
  irsa_role_name        = "cert-manager-route53"
  irsa_namespace        = "cert-manager"
  irsa_service_account  = "cert-manager"
  irsa_policy_json      = data.aws_iam_policy_document.cert_manager_route53.json
  oidc_provider_arn     = module.eks.oidc_provider_arn
  oidc_provider_url     = module.eks.cluster_oidc_issuer_url
  tags                  = local.common_tags
}

module "rds" {
  source = "../../modules/rds"

  project                 = "sahulatkar"
  environment             = var.environment
  vpc_id                  = module.vpc.vpc_id
  allowed_cidr_blocks     = module.vpc.private_subnet_cidr_blocks
  db_subnet_group_name    = module.vpc.database_subnet_group_name
  instance_class          = "db.t3.medium"
  allocated_storage       = 50
  max_allocated_storage   = 100
  multi_az                = false
  backup_retention_period = 7
  deletion_protection     = false
  create_read_replica     = false
  rds_kms_key_arn         = module.kms.rds_key_arn
  secrets_kms_key_arn     = module.kms.secrets_key_arn
  tags                    = local.common_tags
}

module "elasticache" {
  source = "../../modules/elasticache"

  project             = "sahulatkar"
  environment         = var.environment
  vpc_id              = module.vpc.vpc_id
  subnet_ids          = module.vpc.private_subnet_ids
  allowed_cidr_blocks = module.vpc.private_subnet_cidr_blocks
  node_type           = "cache.t3.medium"
  num_cache_clusters  = 1
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
  desired_count          = 1
  db_host                = module.rds.db_instance_endpoint
  db_name                = "sahulatkar"
  db_user                = "sk_admin"
  db_password_secret_arn = var.db_password_secret_arn
  tags                   = local.common_tags
}
