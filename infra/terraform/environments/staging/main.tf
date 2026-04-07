provider "aws" {
  region = var.aws_region
}

module "vpc" {
  source = "../../modules/vpc"
}

module "rds" {
  source = "../../modules/rds"
  vpc_id = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets
}

module "eks" {
  source = "../../modules/eks"
  vpc_id = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets
}
