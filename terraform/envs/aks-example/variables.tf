variable "subscription_id" {
  type        = string
  description = "Subscription to place the example cluster in. There is no default."
}

variable "name" {
  type        = string
  description = "Cluster name."
  default     = "agent-platform"
}

variable "location" {
  type        = string
  description = "Azure region."
  default     = "eastus"
}
