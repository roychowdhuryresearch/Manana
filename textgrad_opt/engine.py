"""BedrockEngine: wraps AWS Bedrock Converse API for TextGrad."""

import os
import boto3
import dotenv
from textgrad.engine.base import EngineLM

dotenv.load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))

DEFAULT_MODEL = "openai.gpt-oss-120b-1:0"


class BedrockEngine(EngineLM):
    """Synchronous Bedrock engine for TextGrad (no extended thinking)."""

    def __init__(self, model: str = DEFAULT_MODEL, max_tokens: int = 4000, temperature: float | None = None):
        self.model_string = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        region = os.getenv("AWS_REGION", "us-east-1")
        self.client = boto3.client("bedrock-runtime", region_name=region)

    def generate(self, prompt, system_prompt=None, **kwargs) -> str:
        # prompt and system_prompt may be Variable objects or plain strings
        user_text = prompt.value if hasattr(prompt, "value") else str(prompt)
        sys_text = system_prompt.value if hasattr(system_prompt, "value") else (system_prompt if system_prompt is not None else "")

        inference_config = {"maxTokens": self.max_tokens}
        if self.temperature is not None:
            inference_config["temperature"] = self.temperature

        request = {
            "modelId": self.model_string,
            "messages": [{"role": "user", "content": [{"text": user_text}]}],
            "inferenceConfig": inference_config,
            "additionalModelRequestFields": {"thinking": {"type": "disabled"}},
        }
        if sys_text:
            request["system"] = [{"text": sys_text}]
        response = self.client.converse(**request)

        content_blocks = response.get("output", {}).get("message", {}).get("content", [])
        for block in content_blocks:
            if "text" in block:
                return block["text"].strip()
        return ""

    def __call__(self, *args, **kwargs):
        return self.generate(*args, **kwargs)
