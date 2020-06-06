module "bank_download_project" {
  source = "git::https://github.com/msb/tf-gcp-project.git"

  project_name         = "Bank Download"
  billing_account_name = local.billing_account_name
  additional_apis      = [
    "sheets.googleapis.com",
    "drive.googleapis.com",
  ]
}
