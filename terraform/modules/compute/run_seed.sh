#!/usr/bin/env bash
# Lanza la tarea del seed, espera a que termine y falla si el contenedor no salió con 0.
set -euo pipefail

TASK_ARN=$(aws ecs run-task \
  --region "$REGION" \
  --cluster "$CLUSTER" \
  --task-definition "$TASK_DEFINITION" \
  --launch-type FARGATE \
  --network-configuration "$NETWORK_CONFIG" \
  --overrides "$OVERRIDES" \
  --query 'tasks[0].taskArn' --output text)

echo "Seed task: $TASK_ARN"
aws ecs wait tasks-stopped --region "$REGION" --cluster "$CLUSTER" --tasks "$TASK_ARN"

EXIT_CODE=$(aws ecs describe-tasks \
  --region "$REGION" --cluster "$CLUSTER" --tasks "$TASK_ARN" \
  --query 'tasks[0].containers[0].exitCode' --output text)

if [ "$EXIT_CODE" != "0" ]; then
  echo "Seed failed (exit code $EXIT_CODE). Logs: CloudWatch, log group of the API, stream api/api/${TASK_ARN##*/}" >&2
  exit 1
fi
echo "Seed OK"
