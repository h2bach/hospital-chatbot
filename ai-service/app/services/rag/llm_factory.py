"""
LLM Factory with OOP Design Patterns.

Architecture:
    - Abstract Factory Pattern: LLMProviderFactory for creating providers
    - Factory Method Pattern: Each provider implements create_llm()
    - Singleton Pattern: Cache working LLM instances per tier
    - Strategy Pattern: Tier strategies with fallback chains

Design Principles:
    1. Model tier mapping is DEFINED IN CODE, not in .env
    2. Model names and API keys are READ FROM .env
    3. Open for extension (add new tiers/providers) without modifying core logic
    4. Singleton cache: reuse instance of working model per tier
    5. Automatic fallback: try models in order until one works
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Literal
from dataclasses import dataclass

from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.config import Settings

logger = logging.getLogger(__name__)

# Type definitions
ModelTier = Literal["cheap", "middle", "strong"]


# ============================================================================
# Exception Classes
# ============================================================================

class LLMFactoryError(Exception):
    """Base exception for LLM factory errors."""
    pass


class ProviderNotSupportedError(LLMFactoryError):
    """Raised when provider is not supported."""
    pass


class ModelConfigError(LLMFactoryError):
    """Raised when model configuration is invalid."""
    pass


class AllModelsFailedError(LLMFactoryError):
    """Raised when all models in fallback chain failed."""
    pass


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ModelSpec:
    """Specification for a model."""
    provider: str  # ollama, google, openai, other
    model_name: str
    
    def __str__(self) -> str:
        return f"{self.provider}:{self.model_name}"


@dataclass
class TierConfig:
    """Configuration for a tier with fallback chain."""
    primary: ModelSpec
    fallbacks: list[ModelSpec]
    
    def all_models(self) -> list[ModelSpec]:
        """Get all models including primary and fallbacks."""
        return [self.primary] + self.fallbacks


# ============================================================================
# Abstract Factory Pattern: LLM Provider Factory
# ============================================================================

class LLMProviderFactory(ABC):
    """Abstract factory for creating LLM providers."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
    
    @abstractmethod
    def create_llm(self, model_name: str) -> Any:
        """Factory method to create LLM instance."""
        pass
    
    @abstractmethod
    def validate_config(self) -> bool:
        """Validate if provider configuration is valid."""
        pass


class OllamaProviderFactory(LLMProviderFactory):
    """Factory for Ollama provider."""
    
    def create_llm(self, model_name: str) -> Any:
        return ChatOllama(
            base_url=self.settings.ollama_base_url,
            model=model_name or self.settings.ollama_model,
            temperature=self.settings.llm_temperature,
            num_predict=self.settings.llm_max_tokens,
            timeout=self.settings.llm_timeout,
        )
    
    def validate_config(self) -> bool:
        # Ollama doesn't need API key, just check if base_url is set
        return bool(self.settings.ollama_base_url)


class GoogleProviderFactory(LLMProviderFactory):
    """Factory for Google GenAI provider."""
    
    def create_llm(self, model_name: str) -> Any:
        if not self.settings.google_api_key:
            raise ModelConfigError("GOOGLE_API_KEY is required")
        
        return ChatGoogleGenerativeAI(
            model=model_name or self.settings.google_model,
            google_api_key=self.settings.google_api_key,
            temperature=self.settings.llm_temperature,
            max_output_tokens=self.settings.llm_max_tokens,
            timeout=self.settings.llm_timeout,
        )
    
    def validate_config(self) -> bool:
        return bool(self.settings.google_api_key and 
                   self.settings.google_api_key != "your-google-api-key-here")


class OpenAIProviderFactory(LLMProviderFactory):
    """Factory for OpenAI provider."""
    
    def create_llm(self, model_name: str) -> Any:
        # OpenAI reads OPENAI_API_KEY from environment automatically
        return ChatOpenAI(
            model=model_name or self.settings.openai_model,
            temperature=self.settings.llm_temperature,
            max_tokens=self.settings.llm_max_tokens,
            timeout=self.settings.llm_timeout,
        )
    
    def validate_config(self) -> bool:
        return bool(self.settings.openai_api_key and
                   self.settings.openai_api_key != "your-openai-api-key-here")


class OtherProviderFactory(LLMProviderFactory):
    """Factory for OpenAI-compatible providers (shopaikey, etc.)."""
    
    def create_llm(self, model_name: str) -> Any:
        if not self.settings.other_api_key:
            raise ModelConfigError("OTHER_API_KEY is required")
        
        return ChatOpenAI(
            model=model_name or self.settings.other_model,
            api_key=self.settings.other_api_key,
            base_url=self.settings.other_base_url,
            temperature=self.settings.llm_temperature,
            max_tokens=self.settings.llm_max_tokens,
            timeout=self.settings.llm_timeout,
        )
    
    def validate_config(self) -> bool:
        return bool(self.settings.other_api_key)


# ============================================================================
# Provider Registry (map provider name to factory class)
# ============================================================================

PROVIDER_FACTORIES: dict[str, type[LLMProviderFactory]] = {
    "ollama": OllamaProviderFactory,
    "google": GoogleProviderFactory,
    "openai": OpenAIProviderFactory,
    "other": OtherProviderFactory,
}


# ============================================================================
# Tier Configuration - DEFINED IN CODE (not in .env)
# ============================================================================

def _build_tier_configs(settings: Settings) -> dict[ModelTier, TierConfig]:
    """
    Build tier configurations with fallback chains.
    
    This is WHERE tier logic is DEFINED.
    Only model names from settings are used, not tier mappings.
    """
    return {
        "cheap": TierConfig(
            primary=ModelSpec("other", settings.other_model),
            fallbacks=[
                ModelSpec("other", "gpt-4o-mini"),
                ModelSpec("google", settings.google_model),
            ]
        ),
        "middle": TierConfig(
            primary=ModelSpec("other", settings.other_model),
            fallbacks=[
                ModelSpec("other", "gpt-4o-mini"),
                ModelSpec("google", settings.google_model),
            ]
        ),
        "strong": TierConfig(
            primary=ModelSpec("other", "gpt-4o"),
            fallbacks=[
                ModelSpec("other", settings.other_model),
                ModelSpec("other", "gpt-4o-mini"),
            ]
        ),
    }


# ============================================================================
# Singleton Cache (per tier)
# ============================================================================

class LLMCache:
    """Singleton cache for LLM instances per tier."""
    
    def __init__(self):
        # Cache structure: {tier: (ModelSpec, LLM instance)}
        self._cache: dict[ModelTier, tuple[ModelSpec, Any]] = {}
    
    def get(self, tier: ModelTier) -> tuple[ModelSpec, Any] | None:
        """Get cached LLM for tier."""
        return self._cache.get(tier)
    
    def set(self, tier: ModelTier, model_spec: ModelSpec, llm: Any) -> None:
        """Cache LLM instance for tier."""
        self._cache[tier] = (model_spec, llm)
        logger.info(f"Cached {model_spec} for tier '{tier}'")
    
    def clear(self) -> None:
        """Clear all cache."""
        self._cache.clear()
        logger.info("LLM cache cleared")


# Global singleton cache instance
_llm_cache = LLMCache()


# ============================================================================
# Main Factory Function
# ============================================================================

def create_llm(
    settings: Settings,
    tier: ModelTier | None = None,
    model_override: str | None = None,
    disable_cache: bool = False,
    disable_fallback: bool = False,
) -> Any:
    """
    Create LLM instance with automatic fallback and singleton cache.
    
    Args:
        settings: Application settings (from .env)
        tier: Model tier (cheap/middle/strong). If None, must provide model_override
        model_override: Direct model specification "provider:model" (bypasses tier)
        disable_cache: Don't use cached instance
        disable_fallback: Fail immediately without trying fallback models
        
    Returns:
        LLM instance ready to use
        
    Raises:
        LLMFactoryError: If unable to create any working LLM
        
    Examples:
        >>> # Use tier system (recommended)
        >>> llm = create_llm(settings, tier="cheap")
        >>> 
        >>> # Direct model override
        >>> llm = create_llm(settings, model_override="other:gpt-4o")
        >>> 
        >>> # Disable fallback (fail fast)
        >>> llm = create_llm(settings, tier="strong", disable_fallback=True)
    """
    
    # Determine model specs to try
    if model_override:
        # Direct override: parse and use single model
        model_specs = [_parse_model_spec(model_override, settings)]
        cache_tier = None  # Don't cache overrides
    elif tier:
        # Use tier configuration
        tier_configs = _build_tier_configs(settings)
        tier_config = tier_configs[tier]
        
        # Check cache first
        if not disable_cache:
            cached = _llm_cache.get(tier)
            if cached:
                cached_spec, cached_llm = cached
                logger.info(f"Using cached {cached_spec} for tier '{tier}'")
                return cached_llm
        
        # Build model list: primary + fallbacks
        if disable_fallback:
            model_specs = [tier_config.primary]
        else:
            model_specs = tier_config.all_models()
        
        cache_tier = tier
    else:
        raise ModelConfigError("Must provide either 'tier' or 'model_override'")
    
    # Try each model in order
    errors = []
    for idx, model_spec in enumerate(model_specs):
        is_primary = idx == 0
        log_prefix = "Primary" if is_primary else f"Fallback {idx}"
        
        try:
            logger.info(f"{log_prefix}: Trying {model_spec}")
            
            # Get provider factory
            factory_class = PROVIDER_FACTORIES.get(model_spec.provider)
            if not factory_class:
                raise ProviderNotSupportedError(
                    f"Provider '{model_spec.provider}' not supported"
                )
            
            # Create factory and validate config
            factory = factory_class(settings)
            if not factory.validate_config():
                raise ModelConfigError(
                    f"Provider '{model_spec.provider}' configuration invalid"
                )
            
            # Create LLM instance
            llm = factory.create_llm(model_spec.model_name)
            
            # Log success
            if not is_primary:
                logger.warning(f"{log_prefix} SUCCESS: Using {model_spec}")
            else:
                logger.info(f"{log_prefix} SUCCESS: {model_spec}")
            
            # Cache if tier-based
            if cache_tier and not disable_cache:
                _llm_cache.set(cache_tier, model_spec, llm)
            
            return llm
            
        except Exception as e:
            error_msg = f"{log_prefix} FAILED ({model_spec}): {type(e).__name__}: {str(e)[:100]}"
            logger.error(error_msg)
            errors.append(error_msg)
            
            # If last attempt, raise aggregate error
            if idx == len(model_specs) - 1:
                all_errors = "\n".join(errors)
                raise AllModelsFailedError(
                    f"All {len(model_specs)} model(s) failed:\n{all_errors}"
                )


def _parse_model_spec(spec: str, settings: Settings) -> ModelSpec:
    """
    Parse model specification string.
    
    Format: "provider:model" or "provider"
    If only provider given, use default model from settings.
    """
    if not spec or not spec.strip():
        raise ModelConfigError("Model specification cannot be empty")
    
    parts = spec.strip().split(":", 1)
    provider = parts[0].lower()
    model_name = parts[1] if len(parts) > 1 else ""
    
    # If no model specified, use default from settings
    if not model_name:
        defaults = {
            "ollama": settings.ollama_model,
            "google": settings.google_model,
            "openai": settings.openai_model,
            "other": settings.other_model,
        }
        model_name = defaults.get(provider, "")
        if not model_name:
            raise ModelConfigError(
                f"No default model configured for provider '{provider}'"
            )
    
    if provider not in PROVIDER_FACTORIES:
        raise ProviderNotSupportedError(
            f"Provider '{provider}' not supported. "
            f"Available: {', '.join(sorted(PROVIDER_FACTORIES.keys()))}"
        )
    
    return ModelSpec(provider, model_name)


# ============================================================================
# Utility Functions
# ============================================================================

def clear_llm_cache() -> None:
    """Clear the LLM singleton cache."""
    _llm_cache.clear()


def get_tier_info(settings: Settings, tier: ModelTier) -> dict:
    """
    Get information about a tier's configuration.
    
    Useful for debugging and monitoring.
    """
    tier_configs = _build_tier_configs(settings)
    config = tier_configs[tier]
    
    return {
        "tier": tier,
        "primary": str(config.primary),
        "fallbacks": [str(spec) for spec in config.fallbacks],
        "cached": _llm_cache.get(tier) is not None,
    }


def get_all_tiers_info(settings: Settings) -> dict[ModelTier, dict]:
    """Get information about all tiers."""
    return {
        tier: get_tier_info(settings, tier)
        for tier in ["cheap", "middle", "strong"]
    }
