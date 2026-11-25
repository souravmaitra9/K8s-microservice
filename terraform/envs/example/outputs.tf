output "cluster_name" {
  description = "EKS cluster name."
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "EKS API endpoint."
  value       = module.eks.cluster_endpoint
}

output "oidc_provider_arn" {
  description = "OIDC provider for a later IRSA binding. The agent workload does not use it."
  value       = module.eks.oidc_provider_arn
}

output "private_subnet_ids" {
  description = "Private subnets the nodes run in."
  value       = module.eks.private_subnet_ids
}
