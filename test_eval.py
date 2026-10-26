"""Offline unit tests. No Snowflake login, model call, or vendor endpoint access."""
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def load_modules():
    def instrument(**kwargs):
        return lambda function: function

    def module(name, **attrs):
        value = types.ModuleType(name)
        for key, item in attrs.items():
            setattr(value, key, item)
        return value

    span = types.SimpleNamespace(
        SpanType=types.SimpleNamespace(GENERATION='generation', RECORD_ROOT='root'),
        RECORD_ROOT=types.SimpleNamespace(INPUT='input', OUTPUT='output'),
    )
    stubs = {
        'dotenv': module('dotenv', load_dotenv=Mock()),
        'snowflake.snowpark': module('snowflake.snowpark', Session=Mock()),
        'trulens.core.otel.instrument': module('instrument', instrument=instrument),
        'trulens.otel.semconv.trace': module('trace', SpanAttributes=span),
        'trulens.apps.app': module('truapp', TruApp=Mock()),
        'trulens.connectors.snowflake': module('connector', SnowflakeConnector=Mock()),
        'trulens.core.run': module('run', RunConfig=Mock()),
    }
    with patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location('app', ROOT / 'app.py')
        app = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(app)
        with patch.dict(sys.modules, {'app': app}):
            spec = importlib.util.spec_from_file_location('runner_under_test', ROOT / 'run_eval.py')
            runner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(runner)
    return app, runner, stubs['dotenv'].load_dotenv


app, runner, dotenv_loader = load_modules()


class InferenceTests(unittest.TestCase):
    def test_ai_complete_binds_prompt_and_model(self):
        session = Mock()
        session.sql.return_value.collect.return_value = [{'RESPONSE': '150'}]
        model = app.CortexCompletionApp(session, 'claude-sonnet-4-5', 'Be accurate')
        self.assertEqual(model.run("quote ' and newline\n"), '150')
        call = session.sql.call_args
        self.assertIn('AI_COMPLETE', call.args[0])
        self.assertNotIn("quote '", call.args[0])
        self.assertEqual(call.kwargs['params'][0], 'claude-sonnet-4-5')
        self.assertIn("quote ' and newline\n", call.kwargs['params'][1])
        self.assertEqual(call.kwargs['params'][2:], [0.0, 1024])

    def test_empty_response_fails(self):
        session = Mock()
        session.sql.return_value.collect.return_value = [{'RESPONSE': None}]
        with self.assertRaises(RuntimeError):
            app.CortexCompletionApp(session, 'model', 'system').run('question')


class ConfigurationTests(unittest.TestCase):
    settings = {
        'SNOWFLAKE_ACCOUNT': 'org-account', 'SNOWFLAKE_USER': 'test_user',
        'SNOWFLAKE_ROLE': 'LLM_EVAL_ROLE', 'SNOWFLAKE_WAREHOUSE': 'TEST_WH',
        'SNOWFLAKE_DATABASE': 'LLM_EVAL_DB', 'SNOWFLAKE_SCHEMA': 'EVAL',
    }

    def test_dotenv_loaded_from_project(self):
        dotenv_loader.assert_called_once_with(ROOT / '.env', override=False)

    def test_sso_uses_only_snowflake_configuration(self):
        fake_session_type = Mock()
        with patch.dict(os.environ, self.settings, clear=True), patch.object(runner, 'Session', fake_session_type):
            runner.create_snowpark_session()
        config = fake_session_type.builder.configs.call_args.args[0]
        self.assertEqual(config['authenticator'], 'externalbrowser')
        self.assertEqual(config['paramstyle'], 'qmark')
        self.assertNotIn('password', config)
        self.assertNotIn('api_key', config)

    def test_password_required_only_for_password_auth(self):
        config = dict(self.settings, SNOWFLAKE_AUTHENTICATOR='snowflake', SNOWFLAKE_PASSWORD='synthetic-test-value')
        fake_session_type = Mock()
        with patch.dict(os.environ, config, clear=True), patch.object(runner, 'Session', fake_session_type):
            runner.create_snowpark_session()
        self.assertEqual(fake_session_type.builder.configs.call_args.args[0]['password'], 'synthetic-test-value')

    def test_missing_connection_value_fails(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                runner.create_snowpark_session()


class RunTests(unittest.TestCase):
    def test_status_poll_waits_for_ingestion(self):
        run = Mock()
        run.get_status.side_effect = ['INVOCATION_IN_PROGRESS', 'INVOCATION_COMPLETED']
        with patch.object(runner.time, 'sleep') as sleep:
            runner.wait_for_status(run, {'INVOCATION_COMPLETED'}, 10, 1)
        sleep.assert_called_once_with(1)

    def test_partial_run_fails(self):
        run = Mock()
        run.get_status.return_value = 'INVOCATION_PARTIALLY_COMPLETED'
        with self.assertRaises(RuntimeError):
            runner.wait_for_status(run, {'INVOCATION_COMPLETED'}, 10, 1)

    def test_timeout_fails_without_claiming_cancellation(self):
        run = Mock()
        run.get_status.return_value = 'INVOCATION_IN_PROGRESS'
        with patch.object(runner.time, 'monotonic', side_effect=[0, 11]):
            with self.assertRaises(TimeoutError):
                runner.wait_for_status(run, {'INVOCATION_COMPLETED'}, 10, 1)
        run.cancel.assert_not_called()

    def test_end_to_end_mock_keeps_candidate_and_judge_separate(self):
        env = {
            'CANDIDATE_MODEL': 'claude-sonnet-4-5', 'JUDGE_MODEL': 'mistral-large2',
            'APP_NAME': 'CORTEX_LLM_EVAL', 'APP_VERSION': 'sonnet_4_5',
            'EVAL_TABLE': 'LLM_EVAL_DB.EVAL.EVAL_CASES', 'SYSTEM_PROMPT': 'Be accurate',
        }
        session = Mock()
        session.table.return_value.select.return_value.limit.return_value.count.return_value = 3
        run = Mock()
        run.get_status.side_effect = ['INVOCATION_COMPLETED', 'COMPLETED']
        run.compute_metrics.return_value = 'Submitted'
        tru_app = Mock()
        tru_app.add_run.return_value = run
        with patch.dict(os.environ, env, clear=True), \
                patch.object(runner, 'TruApp', return_value=tru_app), \
                patch.object(runner, 'RunConfig') as config:
            result = runner.run_evaluation(session)
        self.assertIs(result, run)
        config_values = config.call_args.kwargs
        self.assertEqual(config_values['llm_judge_name'], 'mistral-large2')
        self.assertEqual(config_values['source_type'], 'TABLE')
        self.assertNotIn('RETRIEVAL.QUERY_TEXT', config_values['dataset_spec'])
        run.start.assert_called_once()
        run.compute_metrics.assert_called_once_with(metrics=['correctness', 'answer_relevance', 'coherence'])


if __name__ == '__main__':
    unittest.main()
