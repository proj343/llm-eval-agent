resource "aws_s3_bucket" "data" {
  bucket = "${var.project}-data-${var.environment}"
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    id     = "reports-lifecycle"
    status = "Enabled"

    filter {
      prefix = "reports/"
    }

    transition {
      days          = var.report_retention_days
      storage_class = "GLACIER"
    }

    expiration {
      days = 365
    }
  }

  rule {
    id     = "audio-cleanup"
    status = "Enabled"

    filter {
      prefix = "audio/"
    }

    expiration {
      days = 30
    }
  }
}

# Notification: trigger SQS when audio is uploaded
resource "aws_s3_bucket_notification" "audio_upload" {
  bucket = aws_s3_bucket.data.id

  queue {
    queue_arn     = aws_sqs_queue.eval_jobs.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "audio/"
    filter_suffix = ".mp3"
  }

  queue {
    queue_arn     = aws_sqs_queue.eval_jobs.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "audio/"
    filter_suffix = ".wav"
  }

  depends_on = [aws_sqs_queue_policy.eval_jobs]
}
