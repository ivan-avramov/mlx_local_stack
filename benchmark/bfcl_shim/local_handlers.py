"""BFCL local-handler subclasses that strip our models' thinking preamble before parsing.

Our served gemma-4 / Qwen3.6 emit a reasoning preamble ahead of the function-call list in
prompt mode:
  * gemma-4:  ``<|channel>thought\\n<channel|>[func(args)]``
  * qwen3.6:  ``<think> ... </think>\\n[func(args)]``
bfcl's ``default_decode_ast_prompting`` ast-parses the WHOLE response (wrapping in ``[...]``),
so the preamble turns a correct call into a SyntaxError -> acc=0. These handlers strip the
preamble (keeping the trailing call list) before delegating to the stock decode, which is
purely a parsing fix — it does not touch generation.
"""
import os
import time

from overrides import override

from bfcl_eval.model_handler.local_inference.gemma import GemmaHandler
from bfcl_eval.model_handler.local_inference.qwen import QwenHandler
from bfcl_eval.model_handler.local_inference.qwen_fc import QwenFCHandler


def strip_thinking(text: str) -> str:
    """Drop a leading reasoning/thinking channel, keeping the final answer segment.

    Channel markup (gemma): keep the segment after the LAST ``<channel|>``.
    Think tags (qwen): keep the segment after the LAST ``</think>``.
    Order matters — channel first, then think — so a response carrying both collapses to the
    bare call list. No markers -> returned unchanged (stripped of surrounding whitespace)."""
    if "<channel|>" in text:
        text = text.rsplit("<channel|>", 1)[-1]
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[-1]
    return text.strip()


class _ThinkingStripMixin:
    """Strip the thinking preamble off ``result`` before the stock AST/exec decode.

    Uses ``*args`` so it is agnostic to each handler's exact decode signature (decode_ast takes
    ``(result, language, has_tool_call_tag)``; decode_execute takes ``(result, has_tool_call_tag)``)."""

    def decode_ast(self, result, *args, **kwargs):
        return super().decode_ast(strip_thinking(result), *args, **kwargs)

    def decode_execute(self, result, *args, **kwargs):
        return super().decode_execute(strip_thinking(result), *args, **kwargs)

    def _query_prompting(self, inference_data: dict):
        """Faithful copy of OSSHandler._query_prompting with ONE change: the generation cap
        ``min(4096, ...)`` is raised to ``MLX_BFCL_MAX_TOKENS`` (default 16384). With thinking
        ON (which we keep), a verbose reasoner needs >4096 tokens to finish reasoning AND emit
        the call on harder items; the stock 4096 cap truncates it mid-<think> → false failure.
        We do NOT touch thinking. Also guards max_context_length (the VLM configs expose
        max_position_embeddings=None at top level → bfcl's handler can leave it unusable)."""
        cap = int(os.environ.get("MLX_BFCL_MAX_TOKENS", "16384") or "16384")
        function = inference_data["function"]
        message = inference_data["message"]
        formatted_prompt = self._format_prompt(message, function)
        inference_data["inference_input_log"] = {"formatted_prompt": formatted_prompt}
        input_token_count = len(self.tokenizer.tokenize(formatted_prompt))

        mcl = self.max_context_length
        if not isinstance(mcl, int) or mcl <= 0:
            mcl = 262144  # these models are 256K; top-level max_position_embeddings is None
        if mcl < input_token_count + 2:
            leftover_tokens_count = 1000
        else:
            leftover_tokens_count = min(cap, mcl - input_token_count - 2)

        extra_body = {}
        if hasattr(self, "stop_token_ids"):
            extra_body["stop_token_ids"] = self.stop_token_ids
        if hasattr(self, "skip_special_tokens"):
            extra_body["skip_special_tokens"] = self.skip_special_tokens

        start_time = time.time()
        kw = dict(model=self.model_path_or_id, temperature=self.temperature,
                  prompt=formatted_prompt, max_tokens=leftover_tokens_count, timeout=72000)
        if extra_body:
            kw["extra_body"] = extra_body
        api_response = self.client.completions.create(**kw)
        return api_response, time.time() - start_time


class GemmaEpiHandler(_ThinkingStripMixin, GemmaHandler):
    """gemma-4: prompt mode (gemma's native bfcl mode; no gemma FC handler exists)."""


class QwenEpiHandler(_ThinkingStripMixin, QwenHandler):
    """Qwen prompt mode — kept for prompt-vs-FC comparison; NOT the default H2H handler."""


class QwenFCEpiHandler(_ThinkingStripMixin, QwenFCHandler):
    """Qwen/qwen3_5 FC mode (native <tool_call> format) — the published-comparable handler for
    Qwen-family. QwenFCHandler already separates </think>; the mixin's strip is belt-and-suspenders
    and its _query_prompting raises the 4096 cap so thinking-on generations finish.

    Also normalizes the tool-call schema: Qwen3.6 inconsistently emits ``"parameters"`` instead of
    the ``"arguments"`` key QwenFCHandler hard-requires (KeyError -> false failure). Both are valid
    function-calling conventions, so we alias parameters->arguments before the stock decode."""

    @staticmethod
    @override
    def _extract_tool_calls(input_string):
        calls = QwenFCHandler._extract_tool_calls(input_string)
        out = []
        for c in calls:
            if isinstance(c, dict) and "arguments" not in c and "parameters" in c:
                c = dict(c)
                c["arguments"] = c.pop("parameters")
            out.append(c)
        return out
