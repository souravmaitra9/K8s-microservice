variable "region" {
  type        = string
  description = "AWS region for the example cluster."
  default     = "us-east-1"
}

variable "name" {
  type        = string
  description = "Cluster and VPC name prefix."
  default     = "agent-platform"
}
