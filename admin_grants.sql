-- Optional provisioning template. Review with your Snowflake administrator.
-- Run setup.sql first. The warehouse must already exist.
USE ROLE ACCOUNTADMIN;
CREATE ROLE IF NOT EXISTS LLM_EVAL_ROLE;
GRANT USAGE ON WAREHOUSE LLM_EVAL_WH TO ROLE LLM_EVAL_ROLE;
GRANT USAGE ON DATABASE LLM_EVAL_DB TO ROLE LLM_EVAL_ROLE;
GRANT USAGE ON SCHEMA LLM_EVAL_DB.EVAL TO ROLE LLM_EVAL_ROLE;
GRANT SELECT ON TABLE LLM_EVAL_DB.EVAL.EVAL_CASES TO ROLE LLM_EVAL_ROLE;
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE LLM_EVAL_ROLE;
GRANT USE AI FUNCTION AI_COMPLETE ON ACCOUNT TO ROLE LLM_EVAL_ROLE;
GRANT CREATE EXTERNAL AGENT ON SCHEMA LLM_EVAL_DB.EVAL TO ROLE LLM_EVAL_ROLE;
GRANT CREATE TASK ON SCHEMA LLM_EVAL_DB.EVAL TO ROLE LLM_EVAL_ROLE;
GRANT EXECUTE TASK ON ACCOUNT TO ROLE LLM_EVAL_ROLE;

-- Assign the custom role to the authorized user according to your policy.
-- GRANT ROLE LLM_EVAL_ROLE TO USER <authorized_user>;

-- Inspect model roles and grant only required candidate/judge model roles.
-- Do not assume regional availability or enable cross-region inference here.
SHOW APPLICATION ROLES LIKE 'CORTEX-MODEL%' IN APPLICATION SNOWFLAKE;
-- GRANT APPLICATION ROLE SNOWFLAKE."<actual-model-role-name>"
--     TO ROLE LLM_EVAL_ROLE;

-- The role registering the External Agent owns it. Other viewer/executor roles
-- need USAGE on that object plus appropriate parent/Cortex privileges.
