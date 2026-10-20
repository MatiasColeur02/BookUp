output "zip_path" {
  value = data.archive_file.this.output_path
}

output "zip_hash" {
  value = data.archive_file.this.output_base64sha256
}
