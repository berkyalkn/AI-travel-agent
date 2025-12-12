#!/bin/bash

set -e

DOCKER_USER="berkayalkn"
TAG="v1"

echo "Starting AI Travel Agent Deployment..."
echo "--------------------------------------------------"


echo "Checking Infrastructure Prerequisites..."

if ! oc get secret backend-secrets > /dev/null 2>&1; then
  echo "ERROR: Secret 'backend-secrets' not found!"
  echo "   Please create it first using your .env file:"
  echo "   Command: oc create secret generic backend-secrets --from-env-file=server/.env"
  exit 1
else
  echo "✅ Secret 'backend-secrets' found."
fi

if ! oc get pvc travel-output-pvc > /dev/null 2>&1; then
  echo "⚠️  WARNING: 'travel-output-pvc' not found. Creating it now..."
  
  echo "apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: travel-output-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi" | oc apply -f -
  
  echo "PVC 'travel-output-pvc' created."
else
  echo "PVC 'travel-output-pvc' found."
fi

echo ""


echo "Building and Pushing Microservices..."

services=(
  "server/services/flight-service travel-flight-service"
  "server/services/hotel-service travel-hotel-service"
  "server/services/activity-service travel-activity-service"
  "server/services/geocoding-service travel-geocoding-service"
  "server/services/event-service travel-event-service"
)

for service in "${services[@]}"; do
  set -- $service
  folder=$1
  name=$2
  
  echo "➡️  Processing: $name"
  
  docker build -t $DOCKER_USER/$name:$TAG $folder
  
  docker push $DOCKER_USER/$name:$TAG
  echo "   Done."
done

echo ""


echo "Building and Pushing Orchestrator (Backend)..."

docker build -t $DOCKER_USER/travel-orchestrator:$TAG server
docker push $DOCKER_USER/travel-orchestrator:$TAG

echo "Orchestrator image pushed."
echo ""


echo "Applying Kubernetes YAML configurations..."

oc apply -f openshift/microservices/

oc apply -f openshift/backend.yaml

echo "Waiting for the Orchestrator Route to be assigned..."
sleep 10

BACKEND_HOST=$(oc get route travel-orchestrator-route -o jsonpath='{.spec.host}')

if [ -z "$BACKEND_HOST" ]; then
  echo "ERROR: Could not fetch Backend Route URL. Make sure the service is running."
  exit 1
fi

FULL_BACKEND_URL="http://$BACKEND_HOST"
echo "Backend is live at: $FULL_BACKEND_URL"
echo ""


echo "Building Frontend with API URL..."

docker build \
  --build-arg VITE_API_URL=$FULL_BACKEND_URL \
  -t $DOCKER_USER/travel-frontend:$TAG client

echo "Pushing Frontend Image..."
docker push $DOCKER_USER/travel-frontend:$TAG

echo "Deploying Frontend to OpenShift..."
oc apply -f openshift/frontend.yaml

echo ""
echo "=================================================="
echo "DEPLOYMENT SUCCESSFUL!"
echo "=================================================="
echo "Access your application here:"
FRONTEND_HOST=$(oc get route travel-frontend-route -o jsonpath='{.spec.host}')
echo "http://$FRONTEND_HOST"
echo "=================================================="