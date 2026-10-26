# Snowflake LLM Evaluation with AI_COMPLETE and TruLens

Compare Snowflake-hosted LLMs on the same test dataset before selecting a model for an application or agent. The included example compares Claude Sonnet 4 with Claude Sonnet 4.5.

## What this project does

* Calls candidate models through Snowflake `AI_COMPLETE` using Snowpark SQL.
* Loads Snowflake connection and evaluation settings from a local `.env` file.
* Uses TruLens to register evaluation runs and capture input/output and generation spans.
* Computes managed, server-side correctness, answer relevance, and coherence metrics using a Cortex judge model.
* Publishes results to Snowsight under AI & ML → Evaluations.

No RAG, knowledge-base table, Anthropic API key, OpenAI API key, or direct vendor SDK is required.

The Python wrapper is registered as an External Agent object in Snowflake. “External Agent” is the AI Observability metadata object type; it does not mean that the model is invoked through an external vendor endpoint. See [Snowflake's TruLens tracing documentation](https://docs.snowflake.com/en/user-guide/snowflake-cortex/ai-observability/trace-applications-trulens).

## Scope

The supplied implementation evaluates one LLM completion plus a fixed prompt. It is a model-selection starting point, not a complete test of an agent's tool use, orchestration, or multi-turn behavior.

For end-to-end agent evaluation, replace `CortexCompletionApp.run()` with the actual agent entry point, preserve its prompt/message semantics and state setup, and change only its model configuration between runs. If the application is a native Cortex Agent, use the separate [Cortex Agent evaluation workflow](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-evaluations).

## Repository contents

```text
snowflake_llm_eval/
    README.md
    .env.example
    .gitignore
    requirements.txt
    app.py
    run_eval.py
    setup.sql
    admin_grants.sql
    smoke_test.sql
    query_results.sql
    tests/
        test_eval.py
```

* `app.py`: non-RAG completion adapter with TruLens instrumentation; all inference uses `AI_COMPLETE`.
* `run_eval.py`: configuration, connection setup, run registration, status polling, and metric computation.
* `setup.sql`: evaluation table and synthetic demo cases; does not replace an existing table.
* `admin_grants.sql`: optional grant template for an administrator to review and adapt.
* `smoke_test.sql`: optional candidate/judge inference checks; these incur charges.
* `query_results.sql`: optional trace and warning/error inspection.
* `tests/test_eval.py`: offline tests using mocked dependencies; no Snowflake login or paid inference.

## Prerequisites

* Python 3.11 or newer.
* A Snowflake account and an existing warehouse.
* Access to the candidate Cortex models and the judge model in the approved region/routing configuration.
* A role permitted to register applications, execute evaluation runs, and read the dataset.

Check availability and lifecycle in the target account:

```sql
SHOW CORTEX BASE MODELS;
```

The example identifiers are `claude-4-sonnet` and `claude-sonnet-4-5`. Current documentation lists Sonnet 4 as legacy. Do not assume either candidate or the example judge `mistral-large2` is available in every account. Confirm model access and lifecycle before running the comparison. See [model and regional availability](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-regional-availability).

Both candidate inference and judge evaluation incur usage charges.

## 1. Add the folder to your repository

Extract the archive and place the `snowflake_llm_eval` folder in your repository. Run the following commands from that folder.

```bash
cd snowflake_llm_eval
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1` and copy the template with `Copy-Item .env.example .env`.

Dependencies are bounded ranges, not a customer-tested lock file. Install them together in a clean environment, test against the target Snowflake account, and capture the resolved versions for your deployment.

## 2. Configure .env

Edit the copied `.env` file. No credential file is included in the archive.

```dotenv
SNOWFLAKE_ACCOUNT=your_org-your_account
SNOWFLAKE_USER=your_snowflake_username
SNOWFLAKE_ROLE=LLM_EVAL_ROLE
SNOWFLAKE_WAREHOUSE=LLM_EVAL_WH
SNOWFLAKE_DATABASE=LLM_EVAL_DB
SNOWFLAKE_SCHEMA=EVAL
SNOWFLAKE_AUTHENTICATOR=externalbrowser

CANDIDATE_MODEL=claude-sonnet-4-5
JUDGE_MODEL=mistral-large2
APP_NAME=CORTEX_LLM_EVAL
APP_VERSION=sonnet_4_5
EVAL_TABLE=LLM_EVAL_DB.EVAL.EVAL_CASES
SYSTEM_PROMPT="You are an accurate enterprise assistant. Answer the user's request concisely. If information is insufficient, state that limitation rather than inventing facts."
TEMPERATURE=0
MAX_TOKENS=1024
EVAL_TIMEOUT_SECONDS=1800
EVAL_POLL_SECONDS=5
```

Browser-based Snowflake SSO is the default. For Snowflake password authentication, set `SNOWFLAKE_AUTHENTICATOR=snowflake` and populate `SNOWFLAKE_PASSWORD`. For key-pair authentication, set `SNOWFLAKE_AUTHENTICATOR=SNOWFLAKE_JWT` and populate `SNOWFLAKE_PRIVATE_KEY_FILE`; set `SNOWFLAKE_PRIVATE_KEY_FILE_PWD` if required. The optional fields are documented in `.env.example`.

The runner loads `.env` from the directory containing `run_eval.py`. Explicit process environment variables override values in `.env`.

`CANDIDATE_MODEL` selects the Cortex LLM being tested. `JUDGE_MODEL` selects the independent Cortex evaluator used by managed metrics. Keep the judge fixed between comparison runs.

Never commit `.env`, passwords, keys, or sensitive test records. `.gitignore` excludes `.env` and generated Python files.

## 3. Provision Snowflake objects and role access

In an authorized Snowflake SQL worksheet:

1. Run `setup.sql` to create the database, schema, evaluation table, and synthetic demonstration cases.
2. Confirm the configured warehouse exists. Update all SQL/configuration names consistently if using existing objects.
3. Have your administrator review and adapt `admin_grants.sql`.
4. Assign the evaluation role to the authorized user and grant access to the candidate and judge models according to account policy.

The grant template uses a custom `LLM_EVAL_ROLE`, not `PUBLIC`. Relevant privileges include:

* Usage on the warehouse, database, and schema; SELECT on the evaluation table.
* `SNOWFLAKE.CORTEX_USER` plus permission to call `AI_COMPLETE`.
* `CREATE EXTERNAL AGENT` and `CREATE TASK` on the application schema.
* `EXECUTE TASK` on the account.
* Access to each candidate/judge Cortex model under account model controls.
* USAGE on an existing External Agent if another role created it.

The role that registers a new application owns its External Agent object. Do not grant all models or enable cross-region inference just to bypass a failure. Follow the customer's regional and access policies. See [AI Observability privileges](https://docs.snowflake.com/en/user-guide/snowflake-cortex/ai-observability/reference) and [Cortex access controls](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-privileges-and-access).

Optionally run `smoke_test.sql` as the evaluation role. Each model query incurs inference charges; skip inaccessible or retired models.

## 4. Prepare the evaluation dataset

The default table is `LLM_EVAL_DB.EVAL.EVAL_CASES`:

| Column | Purpose |
|---|---|
| `CASE_ID` | Your test-case identifier. |
| `INPUT` | Input supplied to the application. |
| `GROUND_TRUTH_OUTPUT` | Verified reference answer used for correctness. |

Replace the three synthetic demo cases with representative customer tasks and verified expected answers. Include normal requests, edge cases, insufficient-information cases, and output-format requirements relevant to your application.

Use approved, de-identified data for sensitive workloads. Traces can include prompts, responses, and intermediate values; review access and retention policies before using customer data. Locally executed Python receives the prompts and responses through the authenticated Snowflake session.

Do not regenerate reference answers separately for each candidate. Keep the dataset unchanged for a fair comparison.

## 5. Run Sonnet 4 and Sonnet 4.5

After checking both models are accessible:

```bash
# Baseline: the current Cortex Sonnet 4 model.
python run_eval.py --model claude-4-sonnet --version sonnet_4

# Candidate: Cortex Sonnet 4.5.
python run_eval.py --model claude-sonnet-4-5 --version sonnet_4_5
```

To use the candidate model and application version configured in `.env`:

```bash
python run_eval.py
```

The same `APP_NAME` groups both application versions. Each invocation creates a uniquely named run and prints its identifiers.

Keep the system prompt, dataset, judge, metrics, inference settings, and application behavior unchanged except for the candidate model. A change to the prompt or tool configuration is a separate experiment.

The candidate call is Snowflake SQL, not a direct Anthropic/OpenAI call:

```sql
SELECT AI_COMPLETE(
    model => 'claude-sonnet-4-5',
    prompt => 'Convert 2.5 hours to minutes. Return only the number.',
    model_parameters => {'temperature': 0, 'max_tokens': 1024}
);
```

In `app.py`, Snowpark binds model names, prompt text, and parameters instead of inserting user text into SQL. See [AI_COMPLETE syntax](https://docs.snowflake.com/en/sql-reference/functions/ai_complete-single-string).

## 6. Review in Snowsight

1. Open AI & ML → Evaluations.
2. Select `CORTEX_LLM_EVAL`, or your configured `APP_NAME`.
3. Open the two runs and compare their results.
4. Review aggregate metrics and individual failure cases, including input/output traces and judge explanations.

The configured metrics are:

* `correctness`: alignment with the verified reference answer.
* `answer_relevance`: whether the response addresses the input; relevance alone is not factual correctness.
* `coherence`: internal consistency and logical flow.

No RAG-specific context relevance or groundedness metric is requested. Tool correctness, policy adherence, and task completion may require custom metrics when integrating the full agent.

Human-review a representative sample rather than relying only on aggregate judge scores. The wrapper captures function latency, including SQL/client round-trip time; it does not explicitly map token/cost metadata. Do not assume complete per-call token or model-only latency accounting from this minimal wrapper.

For optional SQL inspection, use `query_results.sql`; adjust application/database/schema names if you changed the defaults.

## Existing Snowflake Notebook session

If the project modules, dependencies, and `.env` configuration are available in your Notebook workspace, reuse the active session:

```python
from snowflake.snowpark.context import get_active_session
from run_eval import run_evaluation

session = get_active_session()
run_evaluation(session, model_name='claude-4-sonnet', app_version='sonnet_4')
run_evaluation(session, model_name='claude-sonnet-4-5', app_version='sonnet_4_5')
```

The Notebook session supplies authentication and role context; the runner's local connection factory is not invoked. The module still loads evaluation settings from its `.env` file.

## Tests and validation

```bash
python -m compileall -q app.py run_eval.py tests
python -m unittest discover -s tests -v
```

The offline tests mock Snowflake/TruLens dependencies. They verify parameter binding, configuration loading, inference responses, polling, and metric submission. They do not verify live SQL compilation, package interoperability, model access, or successful server-side evaluation.

Before customer deployment, perform a live smoke test and a small evaluation in the target account. Retain the tested dependency versions and review the results with a human evaluator.

## Troubleshooting

* Connection/authentication failure: check `.env`, authentication method, active role, and warehouse access.
* Model access or availability error: inspect `SHOW CORTEX BASE MODELS`, model grants, lifecycle restrictions, and approved routing configuration.
* Application missing in Snowsight: verify the active role has USAGE or OWNERSHIP on the External Agent and access to its database/schema.
* Empty or incorrect metrics: verify dataset columns, reference answers, and the `RECORD_ROOT` input/output mappings.
* Ingestion or evaluation still in progress: inspect the printed run name and use `query_results.sql` for warnings/errors.
* Timeout: the script stops waiting; it does not cancel server-side work. Check run status before starting a new run.
* Partial run: this runner fails rather than presenting results for mismatched successful subsets as a complete comparison.

`run.start()` can return before trace ingestion is complete. The runner waits for `INVOCATION_COMPLETED` before calling `run.compute_metrics()`. The latter is a normal Python method that submits asynchronous server-side work; it must not be wrapped in `asyncio.run()`. See the [TruLens Run API](https://www.trulens.org/reference/trulens/core/run/).

## References

* [Evaluate applications with TruLens](https://docs.snowflake.com/en/user-guide/snowflake-cortex/ai-observability/evaluate-applications-trulens)
* [Trace and monitor applications with TruLens](https://docs.snowflake.com/en/user-guide/snowflake-cortex/ai-observability/trace-applications-trulens)
* [AI Observability metrics, runs, and privileges](https://docs.snowflake.com/en/user-guide/snowflake-cortex/ai-observability/reference)
* [AI_COMPLETE single-string reference](https://docs.snowflake.com/en/sql-reference/functions/ai_complete-single-string)
* [Cortex model availability](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-regional-availability)
* [Cortex privileges and model access](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-privileges-and-access)
