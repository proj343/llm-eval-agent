variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod"
  }
}

variable "project" {
  description = "Project name used as a prefix for all resources"
  type        = string
  default     = "llm-eval-agent"
}

variable "lambda_memory_mb" {
  description = "Lambda memory in MB (more memory = more CPU)"
  type        = number
  default     = 3008
}

variable "lambda_timeout_seconds" {
  description = "Lambda timeout in seconds (max 900)"
  type        = number
  default     = 900
}

variable "anthropic_api_key" {
  description = "Anthropic API key — stored in SSM, passed at apply time"
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key — stored in SSM, passed at apply time"
  type        = string
  sensitive   = true
}

variable "assemblyai_api_key" {
  description = "AssemblyAI API key — stored in SSM, passed at apply time"
  type        = string
  sensitive   = true
}

variable "report_retention_days" {
  description = "Days to retain eval reports in S3 before transitioning to Glacier"
  type        = number
  default     = 90
}

variable "alarm_email" {
  description = "Email address for CloudWatch alarm notifications"
  type        = string
  default     = ""
}
