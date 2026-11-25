module "aks" {
  source = "../../modules/aks"

  name     = var.name
  location = var.location

  tags = {
    project    = "agent-platform"
    managed-by = "terraform"
    example    = "true"
  }
}
