resource "aws_ssm_parameter" "anthropic_api_key" {
  name        = "/${var.project}/${var.environment}/ANTHROPIC_API_KEY"
  description = "Anthropic API key for Claude models"
  type        = "SecureString"
  value       = var.anthropic_api_key
}

resource "aws_ssm_parameter" "openai_api_key" {
  name        = "/${var.project}/${var.environment}/OPENAI_API_KEY"
  description = "OpenAI API key for GPT models and Whisper"
  type        = "SecureString"
  value       = var.openai_api_key
}

resource "aws_ssm_parameter" "assemblyai_api_key" {
  name        = "/${var.project}/${var.environment}/ASSEMBLYAI_API_KEY"
  description = "AssemblyAI API key for transcription with speaker diarization"
  type        = "SecureString"
  value       = var.assemblyai_api_key
}
