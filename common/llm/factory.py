"""依設定建立 LLM provider 實例；換模型只需要改 config.yaml，不用改程式碼。"""
from pathlib import Path
from typing import Union

import yaml

from .base import LLMProvider
from .providers.anthropic_provider import AnthropicProvider
from .providers.openai_provider import OpenAIProvider
from .providers.ollama_provider import OllamaProvider

PROVIDERS: dict[str, type[LLMProvider]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "ollama": OllamaProvider,
}


def create_llm(provider: str, model: str, **kwargs) -> LLMProvider:
    # 依名稱查表建立對應的 provider 實例，查不到就直接報錯列出可用選項
    try:
        cls = PROVIDERS[provider]
    except KeyError:
        raise ValueError(f"未知的 LLM provider: {provider!r}，可用選項: {list(PROVIDERS)}")
    return cls(model=model, **kwargs)


def create_llm_from_config(config_path: Union[str, Path]) -> LLMProvider:
    """從 agent 資料夾下的 config.yaml 讀取 llm 區塊並建立 provider。"""
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    llm_cfg = cfg["llm"]
    return create_llm(llm_cfg["provider"], llm_cfg["model"], **llm_cfg.get("params", {}))
