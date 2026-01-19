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

"""Top level agent for data agent multi-agents.

-- it get data from database (e.g., BQ) using NL2SQL
-- then, it use NL2Py to do further data analysis as needed
"""

from google.adk.tools import ToolContext
from google.adk.tools.agent_tool import AgentTool
from .sub_agents import ds_agent, db_agent, db_agent2
from google.cloud import storage

# import requests
# import os
# import json
# import subprocess
# import asyncio
# import urllib3


#  DataBase Agent #1
async def call_db_agent(
    question: str,
    tool_context: ToolContext,
):
    """Tool to call database (nl2sql) agent."""
    print(
        "\n call_db_agent.use_database:"
        f' {tool_context.state["all_db_settings"]["use_database"]}'
    )

    agent_tool = AgentTool(agent=db_agent)

    db_agent_output = await agent_tool.run_async(
        args={"request": question}, tool_context=tool_context
    )
    tool_context.state["db_agent_output"] = db_agent_output
    return db_agent_output


# DataBase Agent #2
async def call_db_agent2(
    question: str,
    tool_context: ToolContext,
):
    """Tool to call database (nl2sql) agent."""
    print(
        "\n call_db_agent2.use_database2:"
        f' {tool_context.state["all_db_settings2"]["use_database"]}'
    )

    agent_tool2 = AgentTool(agent=db_agent2)

    db_agent_output2 = await agent_tool2.run_async(
        args={"request": question}, tool_context=tool_context
    )
    tool_context.state["db_agent_output2"] = db_agent_output2
    return db_agent_output2


# DataScience Agent #3 [ NOT IN USE]
async def call_ds_agent(
    question: str,
    tool_context: ToolContext,
):
    """Tool to call data science (nl2py) agent."""

    if question == "N/A":
        return tool_context.state["db_agent_output"]

    input_data = tool_context.state["query_result"]

    question_with_data = f"""
  Question to answer: {question}

  Actual data to analyze prevoius quesiton is already in the following:
  {input_data}

  """

    agent_tool = AgentTool(agent=ds_agent)

    ds_agent_output = await agent_tool.run_async(
        args={"request": question_with_data}, tool_context=tool_context
    )
    tool_context.state["ds_agent_output"] = ds_agent_output
    return ds_agent_output


# Tool (function) for Apptio Recommendations
async def call_apptio_agent(
    question: str,
    tool_context: ToolContext,
):
    try:
        apptio_agent_output = "apptio agent initiated !"
        storage_client = storage.client.Client()
        bucket = storage_client.bucket("finops-apptio-recommendations")
        
        if "Azure".lower() in question.lower():
            if "compute".lower() in question.lower():
                blob = bucket.blob("azure/azure_compute_recommendations.json")
            elif "disk".lower() in question.lower():
                blob = bucket.blob("azure/azure_disk_recommendations.json")
            elif "sql".lower() in question.lower():
                blob = bucket.blob("azure/azure_sql_recommendations.json")
            # blob = bucket.blob("azure/azure_recommendations.json")
        elif "AWS".lower() in question.lower():
            if "ec2".lower() in question.lower():
                blob = bucket.blob("aws/aws_ec2_recommendations.json")
            elif "s3".lower() in question.lower():
                blob = bucket.blob("aws/aws_s3_recommendations.json")
            elif "rds".lower() in question.lower():
                blob = bucket.blob("aws/aws_rds_recommendations.json")
            elif "asg".lower() in question.lower():
                blob = bucket.blob("aws/aws_ec2_asg_recommendations.json") 
            elif "redshift".lower() in question.lower():
                blob = bucket.blob("aws/aws_redshift_recommendations.json")
            elif "ebs".lower() in question.lower():
                blob = bucket.blob("aws/aws_ebs_recommendations.json")
            # blob = bucket.blob("aws/aws_recommendations.json")
        elif "GCP".lower() in question.lower():
            if "compute".lower() in question.lower():
                blob = bucket.blob("gcp/gcp_compute_recommendations.json")
            elif "disk".lower() in question.lower():
                blob = bucket.blob("gcp/gcp_disk_recommendations.json")
            # blob = bucket.blob("gcp/gcp_recommendations.json")  
        apptio_agent_output = blob.download_as_string()
        # print(apptio_agent_output)
        return apptio_agent_output
    except Exception as e:
        return str(e)