variable "name" {
  type        = string
  description = "Prefix for the VPC, cluster, and IAM roles. Keep it short; it is used in resource names."
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR for the cluster VPC. Nodes are placed in private subnets carved from this range."
  default     = "10.40.0.0/16"
}

variable "kubernetes_version" {
  type        = string
  description = "EKS control plane version."
  default     = "1.31"
}

variable "endpoint_public_access" {
  type        = bool
  description = "Expose the Kubernetes API publicly. Leave this false and reach the API from inside the VPC."
  default     = false
}

variable "node_instance_types" {
  type        = list(string)
  description = "Instance types for the managed node group."
  default     = ["m6i.large"]
}

variable "node_min_size" {
  type        = number
  description = "Minimum size of the managed node group."
  default     = 2
}

variable "node_desired_size" {
  type        = number
  description = "Desired size of the managed node group."
  default     = 2
}

variable "node_max_size" {
  type        = number
  description = "Maximum size of the managed node group."
  default     = 4
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to resources this module creates."
  default     = {}
}
