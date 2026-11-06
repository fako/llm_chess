"""
Anthropic vendor for Datagrowth.

This module lives outside of the datagrowth package for now, but it only depends on datagrowth itself.
It mirrors datagrowth.vendors.openai, so that moving it to datagrowth/vendors/anthropic later is a matter of
moving the directory and replacing register_defaults below with an "anthropic" section in datagrowth.yml.
"""
from typing import Any, ClassVar

from datagrowth.configuration import register_defaults
from datagrowth.configuration.defaults import DATAGROWTH_DEFAULT_CONFIGURATION
from datagrowth.exceptions import DGHttpNoAuthentication
from datagrowth.llm import LLMCosts, LLMModel, LLMVendors
from datagrowth.registry import DATAGROWTH_REGISTRY, Tag
from datagrowth.resources.prompt.pydantic import PromptResource, PromptInputsValidator
import datagrowth.resources.http.extractors.requests  # noqa: F401 registers the requests extractor


# Configuration defaults that belong in datagrowth.yml once this vendor moves into datagrowth.
# Applications set the api_key at runtime with: register_defaults("anthropic", {"api_key": ...})
# Like datagrowth.yml these defaults are the lowest layer, so values that applications registered earlier are kept.
ANTHROPIC_DEFAULTS = {
    "api_key": None,
    "api_version": "2023-06-01",
    "betas": ["server-side-fallback-2026-07-01"],
    "fallbacks": "default",  # re-runs a request on a recommended model server side when a model declines it
    "max_tokens": 16_000,
    "timeout": 600,  # generations with adaptive thinking easily take longer than the 30 second http default
}
register_defaults("anthropic", {
    key: value for key, value in ANTHROPIC_DEFAULTS.items()
    if f"anthropic_{key}" not in DATAGROWTH_DEFAULT_CONFIGURATION
})


ANTHROPIC_DEFAULT_TAG = Tag(category="llm", value="anthropic/default")
ANTHROPIC_OPTIONS = [("max_tokens", int,), ("effort", str,)]
ANTHROPIC_DEFAULT_MODEL = LLMModel(
    identifier="claude-opus-5", vendor=LLMVendors.ANTHROPIC,
    max_inputs=1_000_000, max_outputs=128_000,
    costs=LLMCosts(input_tokens=5.00, output_tokens=25.00, cache_tokens=0.50),  # dollars per million tokens
    options=ANTHROPIC_OPTIONS,
)
DATAGROWTH_REGISTRY.register_llm(ANTHROPIC_DEFAULT_TAG, ANTHROPIC_DEFAULT_MODEL)


class AnthropicPromptResource(PromptResource):

    URI_TEMPLATE = "https://api.anthropic.com/v1/messages"
    NAMESPACE: ClassVar[Tag] = Tag(category="namespace", value="anthropic")
    DEFAULT_MODEL: ClassVar[Tag | None] = ANTHROPIC_DEFAULT_TAG

    SUCCESS_STOP_REASONS: ClassVar[set[str]] = {"end_turn", "stop_sequence"}

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        # The extractor reads http_resource configuration only, so we pass on our own timeout explicitly.
        if self.EXTRACTOR:
            self._extractor = DATAGROWTH_REGISTRY.get_extractor(
                self.EXTRACTOR, overrides={"timeout": self.config.timeout}
            )

    def auth_headers(self) -> dict:
        api_key = self.config.api_key
        if api_key is None:
            raise DGHttpNoAuthentication("Missing anthropic api_key configuration", resource=self)
        return {"x-api-key": api_key}

    def headers(self, *args: Any, **kwargs: Any) -> dict[str, str]:
        headers = super().headers(*args, **kwargs)
        headers["anthropic-version"] = self.config.api_version
        if self.config.betas:
            headers["anthropic-beta"] = ",".join(self.config.betas)
        return headers

    def data(self, prompt: str | None = None, model: str | None = None, **kwargs: Any) -> dict[str, Any]:
        assert model, "Data method expected to get a model name"
        assert prompt, "Data method expected to get a prompt"
        options = kwargs.get("options", {})
        options = dict(options) if isinstance(options, dict) else {}

        data: dict[str, Any] = {
            "model": model,
            "max_tokens": options.pop("max_tokens", self.config.max_tokens),
            "thinking": {"type": "adaptive"},
            "messages": [{"role": "user", "content": prompt}],
        }
        if self.config.fallbacks:
            data["fallbacks"] = self.config.fallbacks
        output_config: dict[str, Any] = {}
        if "effort" in options:
            output_config["effort"] = options.pop("effort")

        template = kwargs.get("template")
        if isinstance(template, str) and template.endswith(".json.tpl"):
            context = kwargs.get("context", {})
            output_config["format"] = {
                "type": "json_schema",
                "schema": context["json_schema"],
            }
        if output_config:
            data["output_config"] = output_config
        return data

    @property
    def stop_reason(self) -> str | None:
        _, data = super(PromptResource, self).content
        return data.get("stop_reason") if isinstance(data, dict) else None

    @property
    def success(self) -> bool:
        if not super().success:
            return False
        return self.stop_reason in self.SUCCESS_STOP_REASONS

    def handle_errors(self) -> None:
        # High-over checks of HTTP errors and wrong types
        super().handle_errors()
        if not super().success:  # failure in http layer, we don't need to handle anything else
            return None
        if self.success:  # all (generated) data is valid, we don't need to handle anything
            return None

        error_message = None
        error_code = None
        stop_reason = self.stop_reason
        if stop_reason == "max_tokens":
            error_code = self.ErrorCodes.MAX_TOKENS_EXCEEDED.value
            error_message = "Anthropic response exceeded maximum output tokens."
        elif stop_reason == "refusal":
            error_code = self.ErrorCodes.CONTENT_FILTER.value
            error_message = "Anthropic models declined to respond to the prompt."
        if error_code is not None and error_message is not None:
            self.update(self._error_resource(self.llm, self.signature, error_code, error_message))
        return None

    @property
    def content(self) -> tuple[str | None, Any]:
        # Do not try to render content when something went wrong
        if not self.success or not self.signature:
            return None, None
        content_type, data = super().content
        assert isinstance(data, dict), f"AnthropicPromptResource has unexpected content of type: {type(data)}"

        # Thinking and fallback blocks are skipped, only generated text is content
        text = "".join(
            block["text"] for block in data.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
        )

        # Parse and return the message
        assert issubclass(self.INPUTS_VALIDATOR, PromptInputsValidator), \
            f"PromptResource needs PromptInputsValidator as INPUTS_VALIDATOR, but found '{self.INPUTS_VALIDATOR}'"
        llm = self._get_llm_definition()
        inputs = self.INPUTS_VALIDATOR.from_llm(llm, *self.signature.args, **self.signature.kwargs)
        if inputs.output:
            return "application/json", inputs.output.model_validate_json(text)
        return "text/plain", text

    ########################
    # Prompt helpers
    ########################

    def get_token_usage(self) -> dict[str, int]:
        if not self.success:
            raise RuntimeError("Can't calculate token usage for failed Resource")
        _, data = super(PromptResource, self).content
        assert isinstance(data, dict), f"AnthropicPromptResource has unexpected content of type: {type(data)}"
        usage = data["usage"]
        prompt = usage.get("input_tokens", 0)
        completion = usage.get("output_tokens", 0)
        return {
            "prompt": prompt,
            "completion": completion,
            "cache_creation": usage.get("cache_creation_input_tokens") or 0,
            "cache_read": usage.get("cache_read_input_tokens") or 0,
            "total": prompt + completion,
        }

    @property
    def served_by(self) -> str | None:
        """
        The model that actually generated the response, which differs from the requested model after a fallback.
        """
        _, data = super(PromptResource, self).content
        return data.get("model") if isinstance(data, dict) else None
