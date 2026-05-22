terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Update bucket/key/region before first apply
  backend "s3" {
    bucket = "your-tf-state-bucket"
    key    = "llm-eval-agent/terraform.tfstate"
    region = "us-east-1"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "llm-eval-agent"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
