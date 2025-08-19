"""LLM client abstraction using Semantic Kernel for Azure OpenAI Chat Completions.

Features:
 - Automatic chunking of large documents to respect model context limits (char-count heuristic).
 - Optional parallel summarization of chunks (ThreadPoolExecutor) for throughput.
 - Two-phase summarization: per-chunk + synthesis step for cohesive final result.
 - Prompt override support via configuration (system + user prompts).

Extension guidance for customers:
 - To emit structured data (e.g., JSON with title/body) instruct the model via the user prompt.
 - If you need token-level control consider switching to the Responses API once available.
 - For very large documents consider semantic chunking (headings) as an enhancement.
"""

from typing import List, Optional, Tuple
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import AppConfig

try:
    from semantic_kernel import Kernel
    from semantic_kernel.connectors.ai.open_ai.services.azure_chat_completion import AzureChatCompletion
    from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.azure_chat_prompt_execution_settings import AzureChatPromptExecutionSettings
    from semantic_kernel.contents import ChatHistory
except Exception:  # pragma: no cover
    Kernel = None  # type: ignore
    AzureChatCompletion = None  # type: ignore
    AzureChatPromptExecutionSettings = None  # type: ignore
    ChatHistory = None  # type: ignore


class LLMClient:
    """Semantic Kernel-based Azure OpenAI Chat Completions client with naive size-based chunking."""

    def __init__(self, cfg: AppConfig):
        if not cfg.azure_openai:
            raise ValueError("Azure OpenAI settings missing in config.json (azure_openai)")
        if Kernel is None or AzureChatCompletion is None:
            raise RuntimeError(
                "semantic-kernel package not installed. Please add 'semantic-kernel>=1.35.0' to requirements and install."
            )
        
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", cfg.azure_openai.endpoint)
        api_key = os.environ.get("AZURE_OPENAI_API_KEY", cfg.azure_openai.api_key)
        self.deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", cfg.azure_openai.deployment)
        self.api_version = os.environ.get("AZURE_OPENAI_API_VERSION", cfg.azure_openai.api_version)
        self.max_chars_per_chunk = cfg.azure_openai.max_chars_per_chunk or 12000
        self.chunk_workers = max(1, getattr(cfg.azure_openai, "chunk_workers", 1))
        
        # Initialize Semantic Kernel
        self.kernel = Kernel()
        self.chat_service = AzureChatCompletion(
            deployment_name=self.deployment,
            api_key=api_key,
            endpoint=endpoint,
            api_version=self.api_version
        )
        self.kernel.add_service(self.chat_service)

    def _get_chat_completion(self, messages: List[dict], max_tokens: int = 300, temperature: float = 0.2) -> str:
        """Helper method to get chat completion synchronously using Semantic Kernel."""
        async def _async_chat_completion():
            chat_history = ChatHistory()
            for message in messages:
                if message["role"] == "system":
                    chat_history.add_system_message(message["content"])
                elif message["role"] == "user":
                    chat_history.add_user_message(message["content"])
                elif message["role"] == "assistant":
                    chat_history.add_assistant_message(message["content"])
            
            settings = AzureChatPromptExecutionSettings(
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            response = await self.chat_service.get_chat_message_content(chat_history, settings)
            return str(response) if response else ""
        
        # Run the async function in the current event loop or create a new one
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If there's already a running loop, we need to run in a thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, _async_chat_completion())
                    return future.result()
            else:
                return loop.run_until_complete(_async_chat_completion())
        except RuntimeError:
            # No event loop, create a new one
            return asyncio.run(_async_chat_completion())

    def _chunk(self, text: str) -> List[str]:
        if len(text) <= self.max_chars_per_chunk:
            return [text]
        chunks: List[str] = []
        start = 0
        step = self.max_chars_per_chunk
        while start < len(text):
            end = min(len(text), start + step)
            chunks.append(text[start:end])
            start = end
        return chunks

    def summarize(self, text: str, system_prompt: Optional[str] = None, user_prompt: Optional[str] = None) -> str:
        """Summarize large text by chunking then synthesizing using Semantic Kernel.

        The method returns raw model text. To request a title + Markdown body, craft the user prompt
        accordingly (see config.json summarize prompt in this project).
        """
        system_prompt = system_prompt or "You are a helpful assistant that writes concise, accurate summaries."
        user_prompt = user_prompt or (
            "Summarize the following content in 8-12 bullet points with headings and key takeaways."
        )
        chunks = self._chunk(text)

        if len(chunks) == 1:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{user_prompt}\n\nCONTENT:\n" + chunks[0]},
            ]
            return self._get_chat_completion(messages, max_tokens=300, temperature=0.2)

        def _summarize_chunk(args: Tuple[int, str, int]) -> Tuple[int, str]:
            idx, content, total = args
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Chunk {idx}/{total}. {user_prompt}\n\nCONTENT:\n" + content},
            ]
            result = self._get_chat_completion(messages, max_tokens=300, temperature=0.2)
            return idx, result or ""

        partial_summaries: List[str] = ["" for _ in chunks]
        if self.chunk_workers > 1 and len(chunks) > 1:
            with ThreadPoolExecutor(max_workers=self.chunk_workers) as ex:
                futures = [ex.submit(_summarize_chunk, (i, c, len(chunks))) for i, c in enumerate(chunks, start=1)]
                for fut in as_completed(futures):
                    idx, result = fut.result()
                    partial_summaries[idx - 1] = result
        else:
            for idx, c in enumerate(chunks, start=1):
                _, result = _summarize_chunk((idx, c, len(chunks)))
                partial_summaries[idx - 1] = result

        synthesis_prompt = (
            "You will receive multiple partial summaries from segments of a document. Produce the final requested "
            "output exactly per the user instructions (which may include returning a title and Markdown body). "
            "Keep factual fidelity."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": synthesis_prompt + "\n\nPARTIAL SUMMARIES:\n" + "\n\n".join(partial_summaries)},
        ]
        return self._get_chat_completion(messages, max_tokens=300, temperature=0.2)
