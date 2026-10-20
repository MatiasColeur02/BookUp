# AWS Academy no permite crear roles IAM: todo (Lambdas, tareas de ECS) usa LabRole.
data "aws_iam_role" "lab" {
  name = "LabRole"
}

data "aws_caller_identity" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}
