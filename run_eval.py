"""Compare Cortex LLMs through AI_COMPLETE; load Snowflake settings from .env."""
from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load before importing TruLens / instrumented app code.
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
os.environ.setdefault("TRULENS_OTEL_TRACING", "1")

from snowflake.snowpark import Session
from trulens.apps.app import TruApp
from trulens.connectors.snowflake import SnowflakeConnector
from trulens.core.run import RunConfig
from app import CortexCompletionApp


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Set {name} in the project .env file")
    return value


def create_snowpark_session() -> Session:
    authenticator = os.getenv("SNOWFLAKE_AUTHENTICATOR", "externalbrowser").strip()
    settings = {
        "account": required("SNOWFLAKE_ACCOUNT"),
        "user": required("SNOWFLAKE_USER"),
        "role": required("SNOWFLAKE_ROLE"),
        "warehouse": required("SNOWFLAKE_WAREHOUSE"),
        "database": required("SNOWFLAKE_DATABASE"),
        "schema": required("SNOWFLAKE_SCHEMA"),
        "authenticator": authenticator,
        "paramstyle": "qmark",
    }
    if authenticator.lower() == "snowflake":
        settings["password"] = required("SNOWFLAKE_PASSWORD")
    elif authenticator.upper() == "SNOWFLAKE_JWT":
        settings["private_key_file"] = required("SNOWFLAKE_PRIVATE_KEY_FILE")
        passphrase = os.getenv("SNOWFLAKE_PRIVATE_KEY_FILE_PWD")
        if passphrase:
            settings["private_key_file_pwd"] = passphrase
    return Session.builder.configs(settings).create()


def status_name(status) -> str:
    return str(getattr(status, "name", status)).rsplit(".", 1)[-1].upper()


def wait_for_status(run, expected: set[str], timeout_seconds: int, poll_seconds: float):
    deadline = time.monotonic() + timeout_seconds
    terminal_errors = {
        "FAILED", "ERROR", "CANCELLED", "CANCELED", "PARTIALLY_COMPLETED",
        "INVOCATION_FAILED", "COMPUTATION_FAILED", "INVOCATION_PARTIALLY_COMPLETED",
    }
    while True:
        status = status_name(run.get_status())
        print(f"Run status: {status}", flush=True)
        if status in expected:
            return status
        if status in terminal_errors:
            raise RuntimeError(
                f"Evaluation ended with {status}. Inspect run logs in Snowsight. "
                "Partial runs are not accepted as successful comparisons."
            )
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Timed out waiting for {sorted(expected)}; last status: {status}. "
                "Server-side work may still be running; check Snowsight."
            )
        time.sleep(poll_seconds)


def run_evaluation(session: Session, model_name: str | None = None,
                   app_version: str | None = None):
    candidate_model = model_name or required("CANDIDATE_MODEL")
    version = app_version or os.getenv("APP_VERSION", candidate_model)
    app_name = os.getenv("APP_NAME", "CORTEX_LLM_EVAL")
    dataset = required("EVAL_TABLE")
    judge_model = required("JUDGE_MODEL")
    timeout = int(os.getenv("EVAL_TIMEOUT_SECONDS", "1800"))
    poll = float(os.getenv("EVAL_POLL_SECONDS", "5"))
    if timeout <= 0 or poll <= 0:
        raise ValueError("Evaluation timeout and polling interval must be positive")

    cases = session.table(dataset).select("CASE_ID", "INPUT", "GROUND_TRUTH_OUTPUT")
    if cases.limit(1).count() == 0:
        raise ValueError(f"Evaluation table is empty: {dataset}")

    app = CortexCompletionApp(
        session=session,
        model_name=candidate_model,
        system_prompt=required("SYSTEM_PROMPT"),
        temperature=float(os.getenv("TEMPERATURE", "0")),
        max_tokens=int(os.getenv("MAX_TOKENS", "1024")),
    )
    tru_app = TruApp(
        app=app,
        app_name=app_name,
        app_version=version,
        connector=SnowflakeConnector(snowpark_session=session),
        main_method=app.run,
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    run_name = f"{version}_{timestamp}"
    run = tru_app.add_run(run_config=RunConfig(
        run_name=run_name,
        description=f"AI_COMPLETE model comparison: {candidate_model}",
        label="sonnet_4_vs_4_5",
        source_type="TABLE",
        dataset_name=dataset,
        dataset_spec={
            "RECORD_ROOT.INPUT": "INPUT",
            "RECORD_ROOT.GROUND_TRUTH_OUTPUT": "GROUND_TRUTH_OUTPUT",
        },
        llm_judge_name=judge_model,
    ))
    print(f"Application: {app_name}; version: {version}; run: {run_name}")
    print(f"Candidate: {candidate_model}; Cortex judge: {judge_model}")
    run.start()
    # Some versions return before server-side trace ingestion is complete.
    wait_for_status(run, {"INVOCATION_COMPLETED"}, timeout, poll)

    # Normal SDK method: it submits asynchronous server-side computation.
    # Do not wrap compute_metrics() in asyncio.run().
    print(run.compute_metrics(metrics=["correctness", "answer_relevance", "coherence"]))
    wait_for_status(run, {"COMPLETED"}, timeout, poll)
    print("Completed. Open Snowsight > AI & ML > Evaluations and compare runs.")
    return run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="Optional Cortex candidate model override")
    parser.add_argument("--version", help="Optional application version override")
    args = parser.parse_args()
    session = create_snowpark_session()
    try:
        run_evaluation(session, args.model, args.version)
    finally:
        session.close()


if __name__ == "__main__":
    main()
