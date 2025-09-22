from enum import Enum


class LLMProvider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"