output "cluster_name" {
  description = "AKS cluster name."
  value       = module.aks.cluster_name
}

output "oidc_issuer_url" {
  description = "OIDC issuer URL."
  value       = module.aks.oidc_issuer_url
}
