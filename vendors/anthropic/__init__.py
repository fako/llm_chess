from typing import ClassVar

from datagrowth.registry import Tag
import datagrowth.resources.storage.file_system  # noqa: F401 registers the file_system storage
from vendors.anthropic.resources import (
    AnthropicPromptResource as AnthropicPromptResourceNoStorage, PromptInputsValidator, ANTHROPIC_DEFAULT_TAG,
    ANTHROPIC_DEFAULT_MODEL, ANTHROPIC_EFFORTS, ANTHROPIC_MODELS, anthropic_llm_tag
)

__all__ = [
    "AnthropicPromptResource",
    "PromptInputsValidator",
    "ANTHROPIC_DEFAULT_TAG",
    "ANTHROPIC_DEFAULT_MODEL",
    "ANTHROPIC_EFFORTS",
    "ANTHROPIC_MODELS",
    "anthropic_llm_tag",
]


class AnthropicPromptResource(AnthropicPromptResourceNoStorage):
    STORAGE: ClassVar[Tag | None] = Tag(category="storage", value="file_system")
