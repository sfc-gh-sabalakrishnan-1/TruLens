"""Non-RAG LLM evaluation adapter. All inference uses Snowflake AI_COMPLETE."""
from __future__ import annotations

from snowflake.snowpark import Session
from trulens.core.otel.instrument import instrument
from trulens.otel.semconv.trace import SpanAttributes


class CortexCompletionApp:
    def __init__(self, session: Session, model_name: str, system_prompt: str,
                 temperature: float = 0.0, max_tokens: int = 1024):
        self.session = session
        self.model_name = model_name
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens

    @instrument(span_type=SpanAttributes.SpanType.GENERATION)
    def complete(self, user_input: str) -> str:
        prompt = (
            f"<system_instructions>\n{self.system_prompt}\n</system_instructions>\n\n"
            f"<user_input>\n{user_input}\n</user_input>\n\nAnswer:"
        )
        # Bind values rather than interpolating user text into SQL.
        rows = self.session.sql(
            """
            SELECT AI_COMPLETE(
                model => ?,
                prompt => ?,
                model_parameters => OBJECT_CONSTRUCT(
                    'temperature', ?, 'max_tokens', ?
                )
            ) AS RESPONSE
            """,
            params=[self.model_name, prompt, self.temperature, self.max_tokens],
        ).collect()
        if not rows or rows[0]["RESPONSE"] is None:
            raise RuntimeError("AI_COMPLETE returned no response")
        return str(rows[0]["RESPONSE"])

    @instrument(
        span_type=SpanAttributes.SpanType.RECORD_ROOT,
        attributes={
            SpanAttributes.RECORD_ROOT.INPUT: "user_input",
            SpanAttributes.RECORD_ROOT.OUTPUT: "return",
        },
    )
    def run(self, user_input: str) -> str:
        # For a full agent evaluation, replace this body with the actual
        # agent entry point while retaining RECORD_ROOT instrumentation.
        return self.complete(user_input)
