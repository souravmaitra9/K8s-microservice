terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }

  # Local state so `terraform validate` works without a remote backend.
  # Point this at an encrypted S3 bucket and a lock table before a real apply.
  backend "local" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      project    = "agent-platform"
      managed-by = "terraform"
      example    = "true"
    }
  }
}
