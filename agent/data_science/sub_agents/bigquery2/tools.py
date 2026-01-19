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

# from .chase_sql import chase_constants

# Assume that `BQ_PROJECT_ID` is set in the environment. See the
# `data_agent` README for more details.

# LLM call from host project 
# llm_project = os.getenv("GOOGLE_CLOUD_PROJECT", "hbl-gcp-prod-finops-prj-spk-d1")
llm_project = "hbl-gcp-prod-finops-prj-spk-d1"

project = os.getenv("BQ_PROJECT_ID", None)
location = os.getenv("GOOGLE_CLOUD_LOCATION", "asia-south1")
#llm_client = Client(vertexai=True, project=project, location=location)
llm_client = Client(vertexai=True, project=llm_project, location=location)

MAX_NUM_ROWS = 700

database_settings2 = None
bq_client = None


def get_bq2_client():
    """Get BigQuery client."""
    global bq_client
    if bq_client is None:
        #bq_client = bigquery.Client(project=get_env_var("BQ_PROJECT_ID2"))
        bq_client = bigquery.Client(project="hbl-gcp-prod-finops-prj-spk-d1")
    return bq_client


# Read BQ Dataset settings
def get_database2_settings():
    """Get database settings."""
    global database_settings2
    if database_settings2 is None:
        database_settings2 = update_database2_settings()
    return database_settings2


# Read BQ Dataset settings for AWS & Azure
def update_database2_settings():
    """Update database settings."""
    global database_settings2
    # ddl_schema2 = get_bigquery2_schema(
    #     get_env_var("BQ_DATASET_ID2"),
    #     client=get_bq2_client(),
    #     project_id=get_env_var("BQ_PROJECT_ID2"),
    # )
    ddl_schema2 = get_bigquery2_schema(
        "multicloud_billing_finops_agent",
        #"FinopsAgentTesting",
        client=get_bq2_client(),
        project_id="hbl-gcp-prod-finops-prj-spk-d1",
    )
    database_settings2 = {
        #"bq_project_id2": get_env_var("BQ_PROJECT_ID2"),
        #"bq_dataset_id2": get_env_var("BQ_DATASET_ID2"),
        "bq_project_id2": "hbl-gcp-prod-finops-prj-spk-d1",
        "bq_dataset_id2": "multicloud_billing_finops_agent",
        "bq_ddl_schema2": ddl_schema2,
        # Include ChaseSQL-specific constants.
        #**chase_constants.chase_sql_constants_dict,
    }
    return database_settings2


# Read BigQuery Table Schema
def get_bigquery2_schema(dataset_id, client=None, project_id=None):
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
def initial_bq2_nl2sql(
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
    print("\n In initial_bq2_nl2sql for Agent2 :", question)
    
    few_shot_examples = """
     
     [Example : **Azure Databricks** ]
     
     **User Question:** Share the Week on Week Azure Meter ( sku) usage along with unit and cost for Meter Category - 'Azure Databricks' for the month of July 2025 , order by Meter (sku) and week . Then list all the details in tabular format with s.no.
     
     **SQL Query:** SELECT EXTRACT(WEEK FROM t.Date) AS week_number, t.MeterName, t.UnitOfMeasure, SUM(t.Quantity) AS TotalQuantity, SUM(t.CostInBillingCurrency) AS TotalCost 
     FROM `hbl-gcp-prod-finops-prj-spk-d1.multicloud_billing_finops_agent.azure_billing` AS t
     WHERE t.MeterCategory = 'Azure Databricks' AND EXTRACT(MONTH FROM t.Date) = 7 AND EXTRACT(YEAR FROM t.Date) = 2025
     GROUP BY week_number, t.MeterName, t.UnitOfMeasure
     ORDER BY t.MeterName, week_number

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

**Think Step-by-Step:** Carefully consider the schema, question, guidelines, Few shot examples and best practices outlined above to generate the correct BigQuery SQL.

   """

    ddl_schema = tool_context.state["database_settings2"]["bq_ddl_schema2"]

    prompt = prompt_template.format(
        MAX_NUM_ROWS=MAX_NUM_ROWS, SCHEMA=ddl_schema, FEW_SHOT_EXAMPLES=few_shot_examples, QUESTION=question
    )
    print("\n NL2SQL passing prompt to Model:", prompt)
    
    response = llm_client.models.generate_content(
        model=os.getenv("BASELINE_NL2SQL_MODEL"),
        contents=prompt,
        config={"temperature": 1.0},  #  config={"temperature": 0.01},
    )

    sql = response.text
    if sql:
        sql = sql.replace("```sql", "").replace("```", "").strip()

    print("\n sql:", sql)

    tool_context.state["sql_query"] = sql

    return sql


# NL2SQL query validation before execution
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
        if "limit" not in sql_string.lower() and ";" not in sql_string.lower():
            sql_string = sql_string + " limit " + str(MAX_NUM_ROWS)

        # 6. #RG : Replace decimal to float
        sql_string = sql_string.replace("Decimal(", "Float(")
        
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
        query_job = get_bq2_client().query(sql_string)
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
