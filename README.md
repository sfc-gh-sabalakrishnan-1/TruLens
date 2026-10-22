# Snowflake TruLens LLM Evaluation Template

This project evaluates a custom Python RAG/LLM application with TruLens and publishes traces, LLM-as-a-judge metrics, and run comparisons to Snowflake AI Observability.

## What this gives you

- The same evaluation dataset for every model version.
- A `base` versus `fine_tuned` run label.
- Snowflake Cortex as the candidate model and TruLens judge model.
- Server-side metrics: correctness, groundedness, context relevance, answer relevance, and coherence.
- Results visible in **Snowsight → AI & ML → Evaluations**.

## 1. Create Snowflake objects

Run `setup.sql` with a role that has permission to create the database/schema and tables.
Replace the demo rows with your real evaluation cases and knowledge base.

## 2. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Configure authentication

Copy `.env.example` to `.env`.

For a named Snowflake connection:

```bash
export SNOWFLAKE_CONNECTION_NAME=my_connection
```

Or unset that value and provide the account/user/password/role/warehouse variables.
Use SSO, key-pair, OAuth, or a PAT in your normal Snowflake connection configuration rather than committing credentials.

## 4. Run the base model evaluation

```bash
CANDIDATE_MODEL=llama3.3-70b \
APP_NAME=customer_rag_eval \
APP_VERSION=base_llama3_3_70b \
python run_eval.py
```

## 5. Run a second model against the same dataset

Replace the model name with the model available in your account:

```bash
CANDIDATE_MODEL=my_fine_tuned_model \
APP_NAME=customer_rag_eval \
APP_VERSION=fine_tuned_model \
python run_eval.py
```

Use the same `EVAL_TABLE`, prompts, retrieval corpus, and metrics. Only change the model or application configuration you want to compare.

## 6. Review results

In Snowsight:

1. Open **AI & ML → Evaluations**.
2. Select the External Agent application `customer_rag_eval`.
3. Open a run for aggregated and per-record scores.
4. Select multiple runs and choose **Compare**.
5. Open a record to inspect the input, retrieved context, output, latency, trace, and judge explanation.

## 7. Replace the demo app

Edit `SnowflakeRAGApp` in `app.py`:

- Replace `retrieve_contexts()` with Cortex Search, vector retrieval, or your existing retriever.
- Replace `generate_completion()` with your application’s model/tool orchestration.
- Keep `RETRIEVAL` span attributes mapped to query and retrieved contexts.
- Keep `RECORD_ROOT` on the top-level method.
- Keep the dataset columns mapped in `run_eval.py`.

For LangChain, LangGraph, or LlamaIndex applications, use the corresponding TruLens auto-instrumentation wrapper instead of the manual decorators.

## Required Snowflake access

The executing role needs access to Cortex models and AI Observability. Use a custom role and grant the required Snowflake database roles/privileges according to your account governance policy.

## Non-RAG Claude agent evaluation

The RAG example above is not required. For a normal agent with no retrieval, use:

- `agent_app.py` — a Claude Sonnet adapter with `RECORD_ROOT` and `GENERATION` spans.
- `run_agent_eval.py` — evaluates the same dataset against two Claude model IDs.
- `agent_setup.sql` — creates a simple input/ground-truth evaluation table.

Create the dataset:

```bash
snowsql -f agent_setup.sql
```

Set your Anthropic credential and the exact model IDs used by your application:

```bash
export ANTHROPIC_API_KEY=...
export CANDIDATE_MODEL=<claude-sonnet-4-model-id>
export APP_NAME=my_agent_eval
export APP_VERSION=sonnet_4
python run_agent_eval.py
```

Then run the same cases against Sonnet 4.5:

```bash
export CANDIDATE_MODEL=<claude-sonnet-4-5-model-id>
export APP_VERSION=sonnet_4_5
python run_agent_eval.py
```

For a non-RAG agent, use `correctness`, `answer_relevance`, and `coherence`. Do not use `context_relevance` or `groundedness` unless your application actually supplies retrieved context. `llm_judge_name` is the evaluator model; it is separate from `CANDIDATE_MODEL`, the Claude model being tested.

If your agent uses tools, keep `RECORD_ROOT` on the top-level agent method and add `@instrument()` to tool functions. The tool calls will then appear in the trace. Replace the `run()` implementation in `agent_app.py` with your actual agent entry point; the evaluation runner does not need to change.
