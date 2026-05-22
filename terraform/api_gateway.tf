resource "aws_apigatewayv2_api" "eval" {
  name          = "${var.project}-${var.environment}"
  protocol_type = "HTTP"
  description   = "HTTP API to submit eval jobs"

  cors_configuration {
    allow_methods = ["POST", "GET"]
    allow_origins = ["*"]
    allow_headers = ["Content-Type", "Authorization"]
    max_age       = 300
  }
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.eval.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      sourceIp       = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      responseLength = "$context.responseLength"
      integrationError = "$context.integrationErrorMessage"
    })
  }
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.eval.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.eval_agent.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 29000  # API GW max; Lambda runs async beyond this
}

# POST /eval — submit an eval job
resource "aws_apigatewayv2_route" "eval_post" {
  api_id    = aws_apigatewayv2_api.eval.id
  route_key = "POST /eval"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

# GET /eval/{job_id} — fetch report from S3
resource "aws_apigatewayv2_route" "eval_get" {
  api_id    = aws_apigatewayv2_api.eval.id
  route_key = "GET /eval/{job_id}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}
