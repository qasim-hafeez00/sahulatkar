variable "domain_name" {
  type        = string
  description = "Apex domain name whose public Route53 hosted zone should be looked up (e.g. sahulatkar.com)"
  default     = "sahulatkar.com"
}
