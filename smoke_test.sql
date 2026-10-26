-- Optional inference checks; each SELECT incurs model usage charges.
-- Run as the same role used by the evaluation after checking model availability.
SHOW CORTEX BASE MODELS;

SELECT AI_COMPLETE('claude-4-sonnet', 'Reply with OK.') AS SONNET_4_RESPONSE;
SELECT AI_COMPLETE('claude-sonnet-4-5', 'Reply with OK.') AS SONNET_4_5_RESPONSE;
SELECT AI_COMPLETE('mistral-large2', 'Reply with OK.') AS JUDGE_RESPONSE;
