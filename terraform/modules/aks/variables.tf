variable "name" {
  type        = string
  description = "Resource group, network, and cluster name. Lowercase letters, numbers, and hyphens."
}

variable "location" {
  type        = string
  description = "Azure region."
  default     = "eastus"
}

variable "kubernetes_version" {
  type        = string
  description = "AKS control plane version. Empty uses the current Azure default."
  default     = null
}

variable "vm_size" {
  type        = string
  description = "VM size for the system node pool."
  default     = "Standard_D4s_v5"
}

variable "node_min" {
  type        = number
  description = "Minimum node count."
  default     = 2
}

variable "node_max" {
  type        = number
  description = "Maximum node count."
  default     = 4
}

variable "sku_tier" {
  type        = string
  description = "Free or Standard. Standard is the paid SLA tier."
  default     = "Free"
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to the resource group and cluster."
  default     = {}
}
