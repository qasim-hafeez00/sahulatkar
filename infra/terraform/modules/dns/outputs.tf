output "zone_id" {
  description = "Route53 hosted zone ID for the apex domain"
  value       = data.aws_route53_zone.root.zone_id
}

output "zone_arn" {
  description = "Route53 hosted zone ARN, scoped for use in IAM policy Resource fields"
  value       = "arn:aws:route53:::hostedzone/${data.aws_route53_zone.root.zone_id}"
}

output "name_servers" {
  description = "Authoritative name servers for the zone, per Route53 - compare against the domain registrar's NS records to confirm delegation"
  value       = data.aws_route53_zone.root.name_servers
}

output "domain_name" {
  description = "Apex domain name that was looked up"
  value       = data.aws_route53_zone.root.name
}
