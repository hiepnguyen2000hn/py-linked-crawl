"""
AI Providers — failover + task routing.

Providers: DeepSeek → OpenAI → Claude (Anthropic)
Router tự động failover khi provider lỗi / hết quota.
"""
from __future__ import annotations
import os, json
from abc import ABC, abstractmethod
from dataclasses import dataclass


# ── Base ──────────────────────────────────────────────────────────────────────

@dataclass
class AIResponse:
    content:  str
    provider: str
    model:    str
    ok:       bool
    error:    str = ""


class AIProvider(ABC):
    name:  str = "base"
    model: str = ""

    @abstractmethod
    def complete(self, prompt: str, temperature: float = 0.3, max_tokens: int = 1000) -> AIResponse:
        ...

    def test_connection(self) -> dict:
        try:
            r = self.complete("Say OK", max_tokens=5)
            return {"ok": r.ok, "message": f"{self.name} OK — model: {self.model}" if r.ok else r.error}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    @property
    def is_configured(self) -> bool:
        return True


# ── DeepSeek ──────────────────────────────────────────────────────────────────

class DeepSeekProvider(AIProvider):
    name  = "deepseek"
    model = "deepseek-chat"

    def __init__(self, api_key: str = "", model: str = ""):
        self._key  = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.model = model or "deepseek-chat"

    @property
    def is_configured(self) -> bool:
        return bool(self._key)

    def complete(self, prompt: str, temperature: float = 0.3, max_tokens: int = 1000) -> AIResponse:
        if not self._key:
            return AIResponse("", self.name, self.model, False, "DEEPSEEK_API_KEY not set")
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self._key, base_url="https://api.deepseek.com")
            resp = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return AIResponse(resp.choices[0].message.content or "", self.name, self.model, True)
        except Exception as e:
            return AIResponse("", self.name, self.model, False, str(e))


# ── OpenAI ────────────────────────────────────────────────────────────────────

class OpenAIProvider(AIProvider):
    name  = "openai"
    model = "gpt-4o-mini"

    def __init__(self, api_key: str = "", model: str = ""):
        self._key  = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model or "gpt-4o-mini"

    @property
    def is_configured(self) -> bool:
        return bool(self._key)

    def complete(self, prompt: str, temperature: float = 0.3, max_tokens: int = 1000) -> AIResponse:
        if not self._key:
            return AIResponse("", self.name, self.model, False, "OPENAI_API_KEY not set")
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self._key)
            resp = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return AIResponse(resp.choices[0].message.content or "", self.name, self.model, True)
        except Exception as e:
            return AIResponse("", self.name, self.model, False, str(e))


# ── Claude (Anthropic) ────────────────────────────────────────────────────────

class ClaudeProvider(AIProvider):
    name  = "claude"
    model = "claude-haiku-4-5-20251001"

    def __init__(self, api_key: str = "", model: str = ""):
        self._key  = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self.model = model or "claude-haiku-4-5-20251001"

    @property
    def is_configured(self) -> bool:
        return bool(self._key)

    def complete(self, prompt: str, temperature: float = 0.3, max_tokens: int = 1000) -> AIResponse:
        if not self._key:
            return AIResponse("", self.name, self.model, False, "ANTHROPIC_API_KEY not set")
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self._key)
            msg = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            content = msg.content[0].text if msg.content else ""
            return AIResponse(content, self.name, self.model, True)
        except Exception as e:
            return AIResponse("", self.name, self.model, False, str(e))


# ── OpenRouter ────────────────────────────────────────────────────────────────

class OpenRouterProvider(AIProvider):
    name  = "openrouter"
    model = "deepseek/deepseek-chat"

    def __init__(self, api_key: str = "", model: str = ""):
        self._key  = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.model = model or "deepseek/deepseek-chat"

    @property
    def is_configured(self) -> bool:
        return bool(self._key)

    def complete(self, prompt: str, temperature: float = 0.3, max_tokens: int = 1000) -> AIResponse:
        if not self._key:
            return AIResponse("", self.name, self.model, False, "OPENROUTER_API_KEY not set")
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self._key, base_url="https://openrouter.ai/api/v1")
            resp = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return AIResponse(resp.choices[0].message.content or "", self.name, self.model, True)
        except Exception as e:
            return AIResponse("", self.name, self.model, False, str(e))


# ── Gemini ────────────────────────────────────────────────────────────────────

class GeminiProvider(AIProvider):
    name  = "gemini"
    model = "gemini-1.5-flash"

    def __init__(self, api_key: str = "", model: str = ""):
        self._key  = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model or "gemini-1.5-flash"

    @property
    def is_configured(self) -> bool:
        return bool(self._key)

    def complete(self, prompt: str, temperature: float = 0.3, max_tokens: int = 1000) -> AIResponse:
        if not self._key:
            return AIResponse("", self.name, self.model, False, "GEMINI_API_KEY not set")
        try:
            import google.generativeai as genai  # type: ignore
            genai.configure(api_key=self._key)
            m = genai.GenerativeModel(self.model)
            resp = m.generate_content(
                prompt,
                generation_config={"temperature": temperature, "max_output_tokens": max_tokens},
            )
            return AIResponse(resp.text or "", self.name, self.model, True)
        except Exception as e:
            return AIResponse("", self.name, self.model, False, str(e))


# ── Router ────────────────────────────────────────────────────────────────────

class AIRouter:
    """
    Failover: thử provider theo thứ tự, dùng provider đầu tiên thành công.
    Task routing: task="bulk" → DeepSeek, task="complex" → Claude/OpenAI.
    """
    def __init__(self, providers: list[AIProvider]):
        self.providers = providers

    @classmethod
    def from_config(cls, config: dict) -> "AIRouter":
        """
        config = {
          "providers": ["deepseek", "openai", "claude", "gemini"],
          "deepseek_api_key": "...",
          "openai_api_key":   "...",
          "claude_api_key":   "...",
          "gemini_api_key":   "...",
          "openai_model":     "gpt-4o",      # optional model override
          "claude_model":     "claude-opus-4-6",
        }
        """
        order = config.get("providers", ["deepseek", "openai", "claude", "gemini"])
        registry: dict[str, AIProvider] = {
            "deepseek":    DeepSeekProvider(config.get("deepseek_api_key", "")),
            "openai":      OpenAIProvider(config.get("openai_api_key", ""),      config.get("openai_model", "")),
            "claude":      ClaudeProvider(config.get("claude_api_key", ""),      config.get("claude_model", "")),
            "gemini":      GeminiProvider(config.get("gemini_api_key", ""),      config.get("gemini_model", "")),
            "openrouter":  OpenRouterProvider(config.get("openrouter_api_key", ""), config.get("openrouter_model", "")),
        }
        providers = [registry[p] for p in order if p in registry]
        return cls(providers or [DeepSeekProvider()])

    def complete(self, prompt: str, temperature: float = 0.3, max_tokens: int = 1000,
                 task: str = "bulk") -> AIResponse:
        """
        task="bulk"    → ưu tiên DeepSeek (rẻ, nhanh)
        task="complex" → ưu tiên Claude/OpenAI (chính xác hơn)
        """
        ordered = self.providers
        if task == "complex":
            # Đẩy Claude + OpenAI lên đầu
            priority = ["claude", "openai", "deepseek", "gemini"]
            ordered  = sorted(self.providers, key=lambda p: priority.index(p.name) if p.name in priority else 99)

        last_error = ""
        for provider in ordered:
            if not provider.is_configured:
                continue
            result = provider.complete(prompt, temperature, max_tokens)
            if result.ok:
                return result
            last_error = f"{provider.name}: {result.error}"
            print(f"[ai-router] {provider.name} failed — {result.error} — trying next")

        return AIResponse("", "none", "", False, f"All providers failed. Last: {last_error}")

    def complete_json(self, prompt: str, temperature: float = 0.2,
                      max_tokens: int = 800, task: str = "bulk") -> dict | None:
        """Gọi complete() và parse JSON từ response."""
        result = self.complete(prompt, temperature, max_tokens, task)
        if not result.ok:
            return None
        raw = result.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"): raw = raw[4:]
        try:
            return json.loads(raw.strip())
        except Exception:
            return None

    def status(self) -> list[dict]:
        return [
            {"name": p.name, "model": p.model, "configured": p.is_configured, "priority": i + 1}
            for i, p in enumerate(self.providers)
        ]
