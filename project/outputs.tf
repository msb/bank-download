output "project_id" {
  value       = module.bank_download_project.project_id
  description = "The GCP project's id."
}

output "state_bucket_name" {
  value = module.bank_download_project.state_bucket_name
  description = "The name of the bucket for terraform state."
}

output "service_account_credentials" {
  sensitive = true
  value     = module.bank_download_project.service_account_credentials
  description = "The project service account credentials."
}
