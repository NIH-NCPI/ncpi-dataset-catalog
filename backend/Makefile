# NCPI Search API - Docker Build & Deploy
# Usage: make <target>
#
# Prerequisites:
#   Prod: aws sso login --profile ncpi-prod-deployer
#
# Quick start:
#   make deploy-dev     # build + push to dev
#   make deploy-prod    # build + push to prod

# Image settings
IMAGE_NAME = ncpi-search-api
IMAGE_TAG ?= latest

# Dev environment
DEV_AWS_PROFILE = excira
DEV_ECR_REPO = 708377107803.dkr.ecr.us-east-1.amazonaws.com/jso-ncpi-dataset-catalog

# Prod environment (update after first terraform apply-prod)
PROD_AWS_PROFILE = ncpi-prod-deployer
PROD_ECR_REPO = 701973344956.dkr.ecr.us-east-1.amazonaws.com/5wu-ncpi-dataset-catalog

AWS_REGION = us-east-1

.PHONY: help build push-dev push-prod deploy-dev deploy-prod

# Default target
help:
	@echo "NCPI Search API - Docker Build & Deploy"
	@echo ""
	@echo "Available targets:"
	@echo "  help          - Show this help message"
	@echo "  build         - Build Docker image locally"
	@echo "  push-dev      - Tag and push image to dev ECR"
	@echo "  push-prod     - Tag and push image to prod ECR"
	@echo "  deploy-dev    - Build + push to dev (all-in-one)"
	@echo "  deploy-prod   - Build + push to prod (all-in-one)"
	@echo ""
	@echo "Quick start:"
	@echo "  make deploy-dev"

# Build Docker image
build:
	@echo "Building Docker image..."
	docker build --platform linux/amd64 -t $(IMAGE_NAME):$(IMAGE_TAG) -f Dockerfile ..

# Push to dev ECR
push-dev:
	@echo "Pushing to dev ECR..."
	@eval "$$(aws configure export-credentials --profile $(DEV_AWS_PROFILE) --format env)" && \
	aws ecr get-login-password --region $(AWS_REGION) | \
		docker login --username AWS --password-stdin $(DEV_ECR_REPO) && \
	docker tag $(IMAGE_NAME):$(IMAGE_TAG) $(DEV_ECR_REPO):$(IMAGE_TAG) && \
	docker push $(DEV_ECR_REPO):$(IMAGE_TAG)

# Push to prod ECR
push-prod:
	@echo "Pushing to prod ECR..."
	@eval "$$(aws configure export-credentials --profile $(PROD_AWS_PROFILE) --format env)" && \
	aws ecr get-login-password --region $(AWS_REGION) | \
		docker login --username AWS --password-stdin $(PROD_ECR_REPO) && \
	docker tag $(IMAGE_NAME):$(IMAGE_TAG) $(PROD_ECR_REPO):$(IMAGE_TAG) && \
	docker push $(PROD_ECR_REPO):$(IMAGE_TAG)

# All-in-one: build + push to dev
deploy-dev: build push-dev
	@echo "Deploy to dev complete."

# All-in-one: build + push to prod
deploy-prod: build push-prod
	@echo "Deploy to prod complete."
