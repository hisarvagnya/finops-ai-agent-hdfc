# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""This file contains the tools used by the database agent."""

import datetime
import logging
from google.cloud import logging as cloud_logging
import os
import re

from data_science.utils.utils import get_env_var
from google.adk.tools import ToolContext
from google.cloud import bigquery
from google.genai import Client

# ====================================================
# LiteLlm integration for HDFC Neev
# import litellm
# from google.adk.agents import LlmAgent
# from google.adk.models.lite_llm import LiteLlm
# ====================================================


logging_client = cloud_logging.Client()
logging_client.setup_logging()

log_name = "HDFC Agent"
custom_logger = logging.getLogger(log_name)


# Direct LLM call from host project 
# Assume that `BQ_PROJECT_ID` is set in the environment. See the
# `data_agent` README for more details.
project = os.getenv("BQ_PROJECT_ID", None)
location = os.getenv("GOOGLE_CLOUD_LOCATION", "asia-south1")

#llm_project = os.getenv("GOOGLE_CLOUD_PROJECT", "hbl-gcp-prod-finops-prj-spk-d1")
llm_project = "hbl-gcp-prod-finops-prj-spk-d1"
logging.info("llm_project: %s", llm_project)

#llm_client = Client(vertexai=True, project=project, location=location)
llm_client = Client(vertexai=True, project=llm_project, location=location)
logging.info("llm_client: %s", llm_client)

MAX_NUM_ROWS = 700

database_settings = None
bq_client = None

def get_bq_client():
    """Get BigQuery client."""
    global bq_client
    if bq_client is None:
        bq_client = bigquery.Client(project=get_env_var("BQ_PROJECT_ID"))
    return bq_client


def get_database_settings():
    """Get database settings."""
    global database_settings
    if database_settings is None:
        database_settings = update_database_settings()
    return database_settings


# Read BQ DataSet details 
def update_database_settings():
    """Update database settings."""
    global database_settings
    ddl_schema = get_bigquery_schema(
        get_env_var("BQ_DATASET_ID"),
        client=get_bq_client(),
        project_id=get_env_var("BQ_PROJECT_ID"),
    )
    database_settings = {
        "bq_project_id": get_env_var("BQ_PROJECT_ID"),
        "bq_dataset_id": get_env_var("BQ_DATASET_ID"),
        "bq_ddl_schema": ddl_schema,
       
    }
    return database_settings


# Read BQ Table Schema
def get_bigquery_schema(dataset_id, client=None, project_id=None):
    """Retrieves schema and generates DDL with example values for a BigQuery dataset.

    Args:
        dataset_id (str): The ID of the BigQuery dataset (e.g., 'my_dataset').
        client (bigquery.Client): A BigQuery client.
        project_id (str): The ID of your Google Cloud Project.

    Returns:
        str: A string containing the generated DDL statements.
    """

    if client is None:
        client = bigquery.Client(project=project_id)

    # dataset_ref = client.dataset(dataset_id)
    dataset_ref = bigquery.DatasetReference(project_id, dataset_id)

    ddl_statements = ""

    for table in client.list_tables(dataset_ref):
        table_ref = dataset_ref.table(table.table_id)
        table_obj = client.get_table(table_ref)

        # Check if table is a view
        if table_obj.table_type != "TABLE":
            continue

        ddl_statement = f"CREATE OR REPLACE TABLE `{table_ref}` (\n"

        for field in table_obj.schema:
            ddl_statement += f"  `{field.name}` {field.field_type}"
            if field.mode == "REPEATED":
                ddl_statement += " ARRAY"
            if field.description:
                ddl_statement += f" COMMENT '{field.description}'"
            ddl_statement += ",\n"

        ddl_statement = ddl_statement[:-2] + "\n);\n\n"

        # Add example values if available (limited to first row)
        rows = client.list_rows(table_ref, max_results=5).to_dataframe()
        if not rows.empty:
            ddl_statement += f"-- Example values for table `{table_ref}`:\n"
            for _, row in rows.iterrows():  # Iterate over DataFrame rows
                ddl_statement += f"INSERT INTO `{table_ref}` VALUES\n"
                example_row_str = "("
                for value in row.values:  # Now row is a pandas Series and has values
                    if isinstance(value, str):
                        example_row_str += f"'{value}',"
                    elif value is None:
                        example_row_str += "NULL,"
                    else:
                        example_row_str += f"{value},"
                example_row_str = (
                    example_row_str[:-1] + ");\n\n"
                )  # remove trailing comma
                ddl_statement += example_row_str

        ddl_statements += ddl_statement

    return ddl_statements


# Generate NL2SQL
def initial_bq_nl2sql(
    question: str,
    tool_context: ToolContext,
) -> str:
    """Generates an initial SQL query from a natural language question.

    Args:
        question (str): Natural language question.
        tool_context (ToolContext): The tool context to use for generating the SQL
          query.

    Returns:
        str: An SQL statement to answer this question.
    """
    
    few_shot_examples = """
     
    [ **Example : SKU Price Change** ]
     
     **User Question:** Analyze and share the list of distinct GCP SKUs of ' Vertex AI ' service for which there are multiple SKU effective price for the same price.tier_start_amount during the invoice month of Oct 2025. Means SKU price was changed during the month.
     
     **SQL Query:** WITH PriceFluctuations AS (SELECT t.sku.id AS sku_id_key, t.sku.description AS sku_description_key, CAST(t.price.tier_start_amount AS FLOAT64) AS tier_start_amount_float_key
    FROM `hbl-srs-logging-prj-spk-3c.hbl_gcp_dataset_billing_export_india.gcp_billing_export_resource_v1_01017D_F95AF4_FDC303` AS t
    WHERE t.service.description = 'Vertex AI' AND t.usage_start_time >= '2025-10-01 00:00:00 UTC' AND t.usage_start_time < '2025-11-01 00:00:00 UTC'
    GROUP BY sku_id_key, sku_description_key, tier_start_amount_float_key
    HAVING COUNT(DISTINCT CAST(t.price.effective_price AS FLOAT64)) > 1 )
    SELECT
    t.sku.id AS sku_id, t.sku.description AS sku_description, CAST(t.price.effective_price AS FLOAT64) AS effective_price, CAST(t.price.tier_start_amount AS FLOAT64) AS tier_start_amount, MIN(t.usage_start_time) AS Date
    FROM `hbl-srs-logging-prj-spk-3c.hbl_gcp_dataset_billing_export_india.gcp_billing_export_resource_v1_01017D_F95AF4_FDC303` AS t
    INNER JOIN PriceFluctuations AS pf
    ON t.sku.id = pf.sku_id_key AND t.sku.description = pf.sku_description_key AND CAST(t.price.tier_start_amount AS FLOAT64) = pf.tier_start_amount_float_key
    WHERE t.service.description = 'Vertex AI' AND t.usage_start_time >= '2025-10-01 00:00:00 UTC' AND t.usage_start_time < '2025-11-01 00:00:00 UTC'
    GROUP BY t.sku.id, t.sku.description, CAST(t.price.effective_price AS FLOAT64), CAST(t.price.tier_start_amount AS FLOAT64)
    ORDER BY sku_id, Date LIMIT 700;
    
    
    [ **Example : New SKUs or Service** ]
     
     **User Question:** Analyze and Extract distinct GCP SKUs of 'Cloud Storage' Service exist for the invoice month of October 2025 but not exist for invoice month of Jan 2025. Then share the list of SKUs ID , Description and Cost with s.no. in tabular format.
     
     **SQL Query:** SELECT t_oct.sku.id AS sku_id, t_oct.sku.description AS sku_description,ROUND(SUM(t_oct.cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(t_oct.credits) c), 0)), 2) AS total_cost_oct_2025, 'INR' as currency
    FROM `hbl-srs-logging-prj-spk-3c.hbl_gcp_dataset_billing_export_india.gcp_billing_export_resource_v1_01017D_F95AF4_FDC303` AS t_oct
    WHERE t_oct.service.description = 'Cloud Storage' AND t_oct.invoice.month = '202510' AND t_oct.sku.id NOT IN (
        SELECT DISTINCT t_jan.sku.id
        FROM `hbl-srs-logging-prj-spk-3c.hbl_gcp_dataset_billing_export_india.gcp_billing_export_resource_v1_01017D_F95AF4_FDC303` AS t_jan
        WHERE t_jan.service.description = 'Cloud Storage' AND t_jan.invoice.month = '202501' ) 
        GROUP BY sku_id, sku_description ORDER BY sku_id ;
        
    
    [ **Example : New Virtual Machine Instances with Intel Machine Family** ]
     
     **User Question:** Analyse the GCP Virtual Machine instances and machine specification for period 20-Oct to 26-Oct-2025 billing data which belongs to Intel machine family and not part of GKE Cluster. Make sure that these instances are not available in period 13-Oct to 19-Oct-2025. Then share the list of Instance name, machine specification and project name order by machine specification with s.no. 
     
     **SQL Query:** SELECT DISTINCT
                    t1.resource.name AS resource_name,
                    t1.project.id AS project_id,
                    (labels.value) AS machine_type,
                    t1.service.description AS service_description
                    FROM
                    `hbl-srs-logging-prj-spk-3c.hbl_gcp_dataset_billing_export_india.gcp_billing_export_resource_v1_01017D_F95AF4_FDC303` AS t1,
                    UNNEST(t1.system_labels) AS labels
                    WHERE
                    labels.key = "compute.googleapis.com/machine_spec"
                    AND REGEXP_CONTAINS(labels.value, r"^(n2|e2|c2|m2|a2|g2|c3|h3|z3|m3|a3|n4|c4|x4|m4|a4)\\-")
                    AND TIMESTAMP_TRUNC(_PARTITIONTIME, DAY) >= TIMESTAMP("2025-10-20")
                    AND TIMESTAMP_TRUNC(_PARTITIONTIME, DAY) <= TIMESTAMP("2025-10-26")
                    AND NOT EXISTS (
                        SELECT 1
                        FROM t1.labels as l
                        WHERE l.key = "goog-k8s-cluster-name"  
                    )
                    AND NOT EXISTS (
                    SELECT 1
                    FROM
                    `hbl-srs-logging-prj-spk-3c.hbl_gcp_dataset_billing_export_india.gcp_billing_export_resource_v1_01017D_F95AF4_FDC303` AS t2
                    WHERE
                    t2.resource.name = t1.resource.name
                    AND t2.project.id = t1.project.id
                    AND TIMESTAMP_TRUNC(_PARTITIONTIME, DAY) >= TIMESTAMP("2025-10-13")
                    AND TIMESTAMP_TRUNC(_PARTITIONTIME, DAY) <= TIMESTAMP("2025-10-19")
                    )
                    GROUP BY
                    resource_name,
                    project_id,
                    service_description, machine_type order by machine_type LIMIT 700 ;
        

    """
    print("\n initial_bq_nl2sql def : few shots building :", few_shot_examples)
     
    prompt_template = """
You are a BigQuery SQL expert tasked with answering user's questions about BigQuery tables by generating SQL queries in the GoogleSql dialect.  Your task is to write a Bigquery SQL query that answers the following question while using the provided context.

**Guidelines:**

- **Table Referencing:** Always use the full table name with the database prefix in the SQL statement.  Tables should be referred to using a fully qualified name with enclosed in backticks (`) e.g. `project_name.dataset_name.table_name`.  Table names are case sensitive.
- **Joins:** Join as few tables as possible. When joining tables, ensure all join columns are the same data type. Analyze the database and the table schema provided to understand the relationships between columns and tables.
- **Aggregations:**  Use all non-aggregated columns from the `SELECT` statement in the `GROUP BY` clause.
- **SQL Syntax:** Return syntactically and semantically correct SQL for BigQuery with proper relation mapping (i.e., project_id, owner, table, and column relation). Use SQL `AS` statement to assign a new name temporarily to a table column or even a table wherever needed. Always enclose subqueries and union queries in parentheses.
- **Column Usage:** Use *ONLY* the column names (column_name) mentioned in the Table Schema. Do *NOT* use any other column names. Associate `column_name` mentioned in the Table Schema only to the `table_name` specified under Table Schema.
- **FILTERS:** You should write query effectively  to reduce and minimize the total rows to be returned. For example, you can use filters (like `WHERE`, `HAVING`, etc. (like 'COUNT', 'SUM', etc.) in the SQL query.
- **LIMIT ROWS:**  The maximum number of rows returned should be less than {MAX_NUM_ROWS}.
- **Data Type** Do Not use the **Decimal** type in SQL query and results. Always replace **Decimal** with **Float64**.
- Strictly Don't use **Decimal** type of columns in output and query, if exist then replace **Decimal** type with **Float64** before generarting the json.

**Schema:**

The database structure is defined by the following table schemas (possibly with sample rows):

```
{SCHEMA}
```

**Few shot examples:**

```
{FEW_SHOT_EXAMPLES}
```

**Natural language question:**

```
{QUESTION}
```

**Think Step-by-Step:** Carefully consider the schema, question, guidelines, few shot examples, and best practices outlined above to generate the correct BigQuery SQL.

   """

    ddl_schema = tool_context.state["database_settings"]["bq_ddl_schema"]

    prompt = prompt_template.format(
        MAX_NUM_ROWS=MAX_NUM_ROWS, SCHEMA=ddl_schema, FEW_SHOT_EXAMPLES=few_shot_examples, QUESTION=question
    )
  
    print("\n initial_bq_nl2sql def prompt building :", prompt)

    logging.info("In initial_bq_nl2sql ....prompt: %s", prompt)
    logging.info("initial_bq_nl2sql`..llm_client: %s", llm_client)
    
    custom_logger.info(f"DEBUG: llm client generated: {llm_client}")
    
    response = llm_client.models.generate_content(
        model="gemini-2.5-flash",
        #model=os.getenv("BASELINE_NL2SQL_MODEL"),
        contents=prompt,
        config={"temperature": 1.0},   # config={"temperature": 0.01},
    )
    
    custom_logger.info(f"DEBUG: response generated: {response}")
    
    logging.info("In initial_bq_nl2sql ....response: %s", response)


    sql = response.text
    if sql:
        sql = sql.replace("```sql", "").replace("```", "").strip()

    print("\n initial_bq_nl2sql def sql:", sql)

    tool_context.state["sql_query"] = sql

    return sql


# Validates NL2SQL Query before execution
def run_bigquery_validation(
    sql_string: str,
    tool_context: ToolContext,
) -> str:
    """Validates BigQuery SQL syntax and functionality.

    This function validates the provided SQL string by attempting to execute it
    against BigQuery in dry-run mode. It performs the following checks:

    1. **SQL Cleanup:**  Preprocesses the SQL string using a `cleanup_sql`
    function
    2. **DML/DDL Restriction:**  Rejects any SQL queries containing DML or DDL
       statements (e.g., UPDATE, DELETE, INSERT, CREATE, ALTER) to ensure
       read-only operations.
    3. **Syntax and Execution:** Sends the cleaned SQL to BigQuery for validation.
       If the query is syntactically correct and executable, it retrieves the
       results.
    4. **Result Analysis:**  Checks if the query produced any results. If so, it
       formats the first few rows of the result set for inspection.

    Args:
        sql_string (str): The SQL query string to validate.
        tool_context (ToolContext): The tool context to use for validation.

    Returns:
        str: A message indicating the validation outcome. This includes:
             - "Valid SQL. Results: ..." if the query is valid and returns data.
             - "Valid SQL. Query executed successfully (no results)." if the query
                is valid but returns no data.
             - "Invalid SQL: ..." if the query is invalid, along with the error
                message from BigQuery.
    """

    def cleanup_sql(sql_string):
        """Processes the SQL string to get a printable, valid SQL string."""

        # 1. Remove backslashes escaping double quotes
        sql_string = sql_string.replace('\\"', '"')

        # 2. Remove backslashes before newlines (the key fix for this issue)
        sql_string = sql_string.replace("\\\n", "\n")  # Corrected regex

        # 3. Replace escaped single quotes
        sql_string = sql_string.replace("\\'", "'")

        # 4. Replace escaped newlines (those not preceded by a backslash)
        sql_string = sql_string.replace("\\n", "\n")

        # 5. Add limit clause if not present
        if "limit" not in sql_string.lower():
            sql_string = sql_string + " limit " + str(MAX_NUM_ROWS)

        # 6. #RG : Replace decimal to float
        sql_string = sql_string.replace("Decimal(", "Float(")
        
        # 7. #RG : Replace ; Limit to Limit
        sql_string = sql_string.replace("; limit", " limit")
        
        return sql_string

    logging.info("Validating SQL: %s", sql_string)
    sql_string = cleanup_sql(sql_string)
    logging.info("Validating SQL (after cleanup): %s", sql_string)

    final_result = {"query_result": None, "error_message": None}

    # More restrictive check for BigQuery - disallow DML and DDL
    if re.search(
        r"(?i)(update|delete|drop|insert|create|alter|truncate|merge)", sql_string
    ):
        final_result["error_message"] = (
            "Invalid SQL: Contains disallowed DML/DDL operations."
        )
        return final_result

    try:
        query_job = get_bq_client().query(sql_string)
        results = query_job.result()  # Get the query results

        if results.schema:  # Check if query returned data
            rows = [
                {
                    key: (
                        value
                        if not isinstance(value, datetime.date)
                        else value.strftime("%Y-%m-%d")
                    )
                    for (key, value) in row.items()
                }
                for row in results
            ][
                :MAX_NUM_ROWS
            ]  # Convert BigQuery RowIterator to list of dicts
            # return f"Valid SQL. Results: {rows}"
            final_result["query_result"] = rows
          
            tool_context.state["query_result"] = rows

        else:
            final_result["error_message"] = (
                "Valid SQL. Query executed successfully (no results)."
            )

    except (
        Exception
    ) as e:  # Catch generic exceptions from BigQuery  # pylint: disable=broad-exception-caught
        final_result["error_message"] = f"Invalid SQL: {e}"

    print("\n run_bigquery_validation final_result: \n", final_result)
    
    return final_result
