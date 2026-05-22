TASK       ?= examples/extraction/task.yaml
MODEL      ?= gpt-4o-mini
COMPARE    ?=
N_CASES    ?= 30
PROVIDER   ?= assemblyai
AUDIO_DIR  ?= examples/extraction/sample_audio
OUTPUT_DIR ?= results

.PHONY: install eval-synthetic eval-audio eval-compare eval-tts lint typecheck test test-unit test-regression update-golden clean

install:
	pip install -e ".[dev]"

## ── Eval targets ──────────────────────────────────────────────────────────────

eval-synthetic:
	PYTHONPATH=src eval-agent run \
		--task $(TASK) \
		--model $(MODEL) \
		--synthetic \
		--n-cases $(N_CASES) \
		--output $(OUTPUT_DIR)

eval-audio:
	PYTHONPATH=src eval-agent run \
		--task $(TASK) \
		--model $(MODEL) \
		--audio $(AUDIO_DIR) \
		--provider $(PROVIDER) \
		--output $(OUTPUT_DIR)

eval-compare:
	@test -n "$(COMPARE)" || (echo "Set COMPARE=<model> to compare, e.g. make eval-compare COMPARE=gpt-4.1" && exit 1)
	PYTHONPATH=src eval-agent run \
		--task $(TASK) \
		--model $(MODEL) \
		--compare $(COMPARE) \
		--synthetic \
		--n-cases $(N_CASES) \
		--output $(OUTPUT_DIR)

eval-tts:
	PYTHONPATH=src eval-agent run \
		--task $(TASK) \
		--model $(MODEL) \
		--synthetic \
		--tts \
		--n-cases $(N_CASES) \
		--output $(OUTPUT_DIR)

## ── Quality targets ──────────────────────────────────────────────────────────

lint:
	ruff check src/ tests/

typecheck:
	mypy src/eval_agent --ignore-missing-imports

test: test-unit test-regression

test-unit:
	PYTHONPATH=src pytest tests/ -v --ignore=tests/test_regression.py -x

test-regression:
	PYTHONPATH=src pytest tests/test_regression.py -v

update-golden:
	PYTHONPATH=src pytest tests/test_regression.py -v --update-golden

## ── Terraform ────────────────────────────────────────────────────────────────

AWS_REGION  ?= us-east-1
AWS_ACCOUNT ?= $(shell aws sts get-caller-identity --query Account --output text)
ECR_URL     ?= $(AWS_ACCOUNT).dkr.ecr.$(AWS_REGION).amazonaws.com/llm-eval-agent
TF_VARS     ?=

tf-init:
	cd terraform && terraform init

tf-plan:
	cd terraform && terraform plan $(TF_VARS)

tf-apply:
	cd terraform && terraform apply $(TF_VARS)

tf-destroy:
	cd terraform && terraform destroy $(TF_VARS)

## ── Docker / ECR ─────────────────────────────────────────────────────────────

docker-build:
	docker build -t llm-eval-agent:latest .

docker-push: docker-build
	aws ecr get-login-password --region $(AWS_REGION) | \
		docker login --username AWS --password-stdin $(ECR_URL)
	docker tag llm-eval-agent:latest $(ECR_URL):latest
	docker push $(ECR_URL):latest

deploy: docker-push
	aws lambda update-function-code \
		--function-name llm-eval-agent-prod \
		--image-uri $(ECR_URL):latest \
		--region $(AWS_REGION)
	@echo "Deployed ✓"

## ── Housekeeping ─────────────────────────────────────────────────────────────

clean:
	rm -rf results/*.md results/*.json
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
