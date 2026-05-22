resource "aws_sqs_queue" "eval_jobs_dlq" {
  name                      = "${var.project}-jobs-dlq-${var.environment}"
  message_retention_seconds = 1209600  # 14 days
}

resource "aws_sqs_queue" "eval_jobs" {
  name                       = "${var.project}-jobs-${var.environment}"
  visibility_timeout_seconds = 960  # > lambda timeout so in-flight jobs don't reappear
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 20  # long polling

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.eval_jobs_dlq.arn
    maxReceiveCount     = 3
  })
}

# Allow S3 to send messages to the queue (audio upload trigger)
data "aws_iam_policy_document" "sqs_s3_send" {
  statement {
    sid     = "AllowS3Send"
    actions = ["sqs:SendMessage"]
    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }
    resources = [aws_sqs_queue.eval_jobs.arn]
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_s3_bucket.data.arn]
    }
  }
}

resource "aws_sqs_queue_policy" "eval_jobs" {
  queue_url = aws_sqs_queue.eval_jobs.id
  policy    = data.aws_iam_policy_document.sqs_s3_send.json
}

# Wire SQS → Lambda
resource "aws_lambda_event_source_mapping" "sqs_to_lambda" {
  event_source_arn                   = aws_sqs_queue.eval_jobs.arn
  function_name                      = aws_lambda_function.eval_agent.arn
  batch_size                         = 1  # one eval job per Lambda invocation
  maximum_batching_window_in_seconds = 0
}
