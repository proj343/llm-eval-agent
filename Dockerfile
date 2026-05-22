FROM public.ecr.aws/lambda/python:3.11

WORKDIR ${LAMBDA_TASK_ROOT}

# Install dependencies first (layer-cached separately from source)
COPY pyproject.toml .
RUN pip install --no-cache-dir boto3 && \
    pip install --no-cache-dir -e "." --no-deps && \
    pip install --no-cache-dir \
        anthropic \
        openai \
        assemblyai \
        jiwer \
        pydantic \
        pyyaml \
        python-dotenv

# Copy source and examples
COPY src/ src/
COPY examples/ examples/

ENV PYTHONPATH="${LAMBDA_TASK_ROOT}/src"

CMD ["eval_agent.lambda_handler.handler"]
