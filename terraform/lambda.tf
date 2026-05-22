data "aws_caller_identity" "current" {}

locals {
  ecr_image_uri = "${aws_ecr_repository.eval_agent.repository_url}:latest"
}

resource "aws_lambda_function" "eval_agent" {
  function_name = "${var.project}-${var.environment}"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = local.ecr_image_uri
  timeout       = var.lambda_timeout_seconds
  memory_size   = var.lambda_memory_mb

  environment {
    variables = {
      ENVIRONMENT            = var.environment
      S3_BUCKET              = aws_s3_bucket.data.bucket
      SSM_PREFIX             = "/${var.project}/${var.environment}"
      ANTHROPIC_API_KEY_PATH = aws_ssm_parameter.anthropic_api_key.name
      OPENAI_API_KEY_PATH    = aws_ssm_parameter.openai_api_key.name
      ASSEMBLYAI_API_KEY_PATH = aws_ssm_parameter.assemblyai_api_key.name
    }
  }

  logging_config {
    log_format = "JSON"
    log_group  = aws_cloudwatch_log_group.lambda.name
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic,
    aws_cloudwatch_log_group.lambda,
  ]
}

# Allow API Gateway to invoke Lambda
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.eval_agent.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.eval.execution_arn}/*/*"
}
