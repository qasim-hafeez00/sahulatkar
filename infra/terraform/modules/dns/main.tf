# Looks up the pre-existing public Route53 hosted zone for the apex domain.
#
# ASSUMPTION: sahulatkar.com is already registered and delegated to Route53
# (either registered directly through Route53, or registered elsewhere with
# its NS records pointed at a Route53-hosted zone). This module intentionally
# does NOT create the zone with `aws_route53_zone` - if the zone does not
# already exist, this data source lookup will fail at `terraform plan` time
# with a "no matching Route53Zone found" error, which is the desired signal
# to go create/delegate the zone (or swap this data source for a resource)
# before proceeding.
data "aws_route53_zone" "root" {
  name         = var.domain_name
  private_zone = false
}
