# src/ie_extractor.py
import json
import re

BASE_MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"
ADAPTER_ID = "alifabdulR/Qwen-2.5-3B-Information-Extraction2"

# Qwen2.5-Instruct chat format
_SYSTEM = (
    "You are an information extraction assistant. "
    "Extract leadership personnel from text and return ONLY a JSON array."
)
_USER_TEMPLATE = """\
Extract all leadership personnel (CEO, CTO, CFO, COO, Founder, Co-founder, \
Director, President, Managing Director, Giám đốc, Tổng giám đốc, Chủ tịch) \
from the following text.
Return ONLY a JSON array like: [{{"name": "...", "title": "..."}}]
If none found, return []

Text:
{text}"""


class IEExtractor:
    """Load Qwen2.5-3B-Instruct + LoRA adapter for leadership extraction."""

    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._torch = None

    def _load(self):
        if self._model is not None:
            return
        import torch
        from transformers import Qwen2ForCausalLM, AutoTokenizer
        from peft import PeftModel

        self._torch = torch
        print(f"[IE] Loading base model {BASE_MODEL_ID} (CPU, ~6GB, first time takes a while)...")
        self._tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID)
        base = Qwen2ForCausalLM.from_pretrained(
            BASE_MODEL_ID,
            torch_dtype=torch.float32,
            device_map="cpu",
        )
        print(f"[IE] Applying LoRA adapter {ADAPTER_ID}...")
        self._model = PeftModel.from_pretrained(base, ADAPTER_ID)
        self._model.eval()
        print("[IE] Model ready.")

    def extract(self, text: str) -> list[dict]:
        """Extract [{name, title}] from text. Returns [] if none found."""
        self._load()
        truncated = text[:2000]
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _USER_TEMPLATE.format(text=truncated)},
        ]
        prompt = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self._tokenizer(prompt, return_tensors="pt")
        with self._torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=256,
                do_sample=False,
                pad_token_id=self._tokenizer.eos_token_id,
            )
        generated = self._tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
        )
        return self._parse(generated)

    def _parse(self, text: str) -> list[dict]:
        try:
            match = re.search(r"\[.*?\]", text, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return [
                    d for d in data
                    if isinstance(d, dict) and "name" in d and "title" in d
                ]
        except Exception:
            pass
        return []
