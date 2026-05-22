output "api_endpoint" {
  description = "HTTP API Gateway endpoint — POST /eval to submit a job"
  value       = "${aws_apigatewayv2_api.eval.api_endpoint}/eval"
}

output "s3_audio_bucket" {
  description = "Upload audio files here: s3://<bucket>/audio/"
  value       = aws_s3_bucket.data.bucket
}

output "s3_reports_prefix" {
  description = "Eval reports are written here"
  value       = "s3://${aws_s3_bucket.data.bucket}/reports/"
}

output "ecr_repository_url" {
  description = "Push your Docker image here before deploying Lambda"
  value       = aws_ecr_repository.eval_agent.repository_url
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.eval_agent.function_name
}

output "sqs_queue_url" {
  description = "SQS queue URL for async eval job submission"
  value       = aws_sqs_queue.eval_jobs.url
}

output "cloudwatch_dashboard_url" {
  description = "CloudWatch dashboard"
  value       = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=${aws_cloudwatch_dashboard.eval_agent.dashboard_name}"
}
