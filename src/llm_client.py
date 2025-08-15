"""LLM client abstraction (Azure OpenAI Chat Completions).

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
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import AppConfig

try:
    from openai import AzureOpenAI  # type: ignore
except Exception:  # pragma: no cover
    AzureOpenAI = None  # type: ignore


class LLMClient:
    """Minimal Azure OpenAI Chat Completions client with naive size-based chunking."""

    def __init__(self, cfg: AppConfig):
        if not cfg.azure_openai:
            raise ValueError("Azure OpenAI settings missing in config.json (azure_openai)")
        if AzureOpenAI is None:
            raise RuntimeError(
                "openai package not installed. Please add 'openai>=1.30.0' to requirements and install."
            )
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", cfg.azure_openai.endpoint)
        api_key = os.environ.get("AZURE_OPENAI_API_KEY", cfg.azure_openai.api_key)
        self.deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", cfg.azure_openai.deployment)
        self.api_version = os.environ.get("AZURE_OPENAI_API_VERSION", cfg.azure_openai.api_version)
        self.max_chars_per_chunk = cfg.azure_openai.max_chars_per_chunk or 12000
        self.chunk_workers = max(1, getattr(cfg.azure_openai, "chunk_workers", 1))
        self.client = AzureOpenAI(api_key=api_key, api_version=self.api_version, azure_endpoint=endpoint)

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
        """Summarize large text by chunking then synthesizing.

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
            resp = self.client.chat.completions.create(
                model=self.deployment,
                messages=messages,
                temperature=0.2,
                max_tokens=300,
            )
            return resp.choices[0].message.content if resp.choices else ""

        def _summarize_chunk(args: Tuple[int, str, int]) -> Tuple[int, str]:
            idx, content, total = args
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Chunk {idx}/{total}. {user_prompt}\n\nCONTENT:\n" + content},
            ]
            resp = self.client.chat.completions.create(
                model=self.deployment,
                messages=messages,
                temperature=0.2,
                max_tokens=300,
            )
            partial = resp.choices[0].message.content if resp.choices else ""
            return idx, (partial or "")

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
        final = self.client.chat.completions.create(
            model=self.deployment,
            messages=messages,
            temperature=0.2,
            max_tokens=300,
        )
        return final.choices[0].message.content if final.choices else ""
