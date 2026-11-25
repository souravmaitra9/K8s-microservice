module "eks" {
  source = "../../modules/eks"

  name                   = var.name
  kubernetes_version     = "1.31"
  endpoint_public_access = false

  tags = {
    environment = "example"
  }
}
