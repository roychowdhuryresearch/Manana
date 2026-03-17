"""Async LLM client using AWS Bedrock.

All model calls are routed through Amazon Bedrock's Converse API.
Default model: openai.gpt-oss-120b-1:0
"""

import os
import asyncio
import random
import boto3
import dotenv

dotenv.load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))

DEFAULT_MODEL = "openai.gpt-oss-120b-1:0"


class LLMClient:
    """Async LLM client using AWS Bedrock Converse API."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        thinking_budget: int = 6000,
        max_tokens: int = 16000,
        max_concurrency: int = 8,
        region: str | None = None,
    ):
        self.model = model
        self.thinking_budget = thinking_budget
        self.max_tokens = max_tokens
        self.semaphore = asyncio.Semaphore(max_concurrency)

        region = region or os.getenv("AWS_REGION", "us-east-1")
        self.bedrock = boto3.client("bedrock-runtime", region_name=region)

    async def close(self):
        """No-op — boto3 client doesn't need explicit close."""
        pass

    def _call_sync(
        self,
        system_prompt: str,
        user_content: str,
    ) -> tuple[str, str]:
        """Synchronous Bedrock Converse call. Returns (thinking, content)."""
        kwargs = {
            "modelId": self.model,
            "messages": [
                {"role": "user", "content": [{"text": user_content}]},
            ],
            "system": [{"text": system_prompt}],
            "inferenceConfig": {"maxTokens": self.max_tokens},
        }

        response = self.bedrock.converse(**kwargs)

        output_message = response.get("output", {}).get("message", {})
        content_blocks = output_message.get("content", [])

        thinking = ""
        text = ""
        for block in content_blocks:
            if "text" in block:
                text = block["text"]
            elif "reasoningContent" in block:
                rc = block["reasoningContent"]
                if "reasoningText" in rc:
                    thinking = rc["reasoningText"].get("text", "")

        return thinking.strip(), text.strip()

    async def call(
        self,
        system_prompt: str,
        user_content: str,
        max_retries: int = 6,
    ) -> tuple[str, str]:
        """Make an LLM call via Bedrock. Returns (thinking/reasoning, content)."""
        for attempt in range(max_retries):
            try:
                async with self.semaphore:
                    return await asyncio.to_thread(
                        self._call_sync, system_prompt, user_content,
                    )
            except Exception as e:
                msg = str(e).lower()
                retryable = any(s in msg for s in [
                    "throttl", "rate", "429", "timeout", "temporar",
                    "overload", "503", "502", "500", "connection",
                ])
                if not retryable or attempt == max_retries - 1:
                    print(f"[ERROR] Bedrock call failed: {e}")
                    return "", ""
                await asyncio.sleep(0.8 * (2 ** attempt) + random.random() * 0.3)
        return "", ""

    async def call_batch(
        self,
        system_prompt: str,
        user_contents: list[tuple[str, str]],  # [(id, content), ...]
        on_complete=None,
    ) -> dict[str, tuple[str, str]]:
        """Run multiple calls concurrently. Returns {id: (thinking, content)}."""
        results = {}

        async def _run_one(item_id, content):
            r, c = await self.call(system_prompt, content)
            results[item_id] = (r, c)
            if on_complete:
                on_complete(item_id, r, c)

        tasks = [_run_one(item_id, content) for item_id, content in user_contents]
        await asyncio.gather(*tasks)
        return results
