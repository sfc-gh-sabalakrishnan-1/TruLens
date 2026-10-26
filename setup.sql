-- Run in a Snowflake SQL worksheet using an authorized provisioning role.
-- Creates demo objects; does not replace existing evaluation tables.
CREATE DATABASE IF NOT EXISTS LLM_EVAL_DB;
CREATE SCHEMA IF NOT EXISTS LLM_EVAL_DB.EVAL;
CREATE TABLE IF NOT EXISTS LLM_EVAL_DB.EVAL.EVAL_CASES (
    CASE_ID NUMBER,
    INPUT VARCHAR,
    GROUND_TRUTH_OUTPUT VARCHAR
);

MERGE INTO LLM_EVAL_DB.EVAL.EVAL_CASES t
USING (
    SELECT column1 AS CASE_ID, column2 AS INPUT, column3 AS GROUND_TRUTH_OUTPUT
    FROM VALUES
    (1, 'Convert 2.5 hours to minutes. Return only the number.', '150'),
    (2, 'A shipment was due on June 10 and arrived on June 13. How many days late was it?', 'The shipment was 3 days late.'),
    (3, 'Based only on this note, list the confirmed conditions: Patient has hypertension; diabetes is suspected but not confirmed.', 'Hypertension is the only confirmed condition. Diabetes is suspected, not confirmed.')
) s
ON t.CASE_ID = s.CASE_ID
WHEN NOT MATCHED THEN INSERT (CASE_ID, INPUT, GROUND_TRUTH_OUTPUT)
VALUES (s.CASE_ID, s.INPUT, s.GROUND_TRUTH_OUTPUT);

-- Check availability/lifecycle before attempting either comparison run.
SHOW CORTEX BASE MODELS;

-- Smoke tests; each incurs inference charges. Run only for accessible models.
-- SELECT AI_COMPLETE('claude-4-sonnet', 'Reply with OK.');
-- SELECT AI_COMPLETE('claude-sonnet-4-5', 'Reply with OK.');
-- SELECT AI_COMPLETE('mistral-large2', 'Reply with OK.');
