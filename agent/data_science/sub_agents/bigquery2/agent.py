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

"""Database Agent: get data from database (BigQuery) using NL2SQL."""

import os

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types
from .prompts import return_instructions_bigquery
from . import tools
# from .chase_sql import chase_db_tools


# ====================================================
# LiteLlm integration for HDFC Neev
# import litellm
# from google.adk.agents import LlmAgent
# from google.adk.models.lite_llm import LiteLlm
# ====================================================


NL2SQL_METHOD = os.getenv("NL2SQL_METHOD", "BASELINE")


def setup_before_agent_call(callback_context: CallbackContext) -> None:
    """Setup the agent."""

    if "database_settings2" not in callback_context.state:
        callback_context.state["database_settings2"] = \
            tools.get_database2_settings()


# Sub Agent 2 for AWS & Azure
database_agent = Agent(
    #model=os.getenv("BIGQUERY_AGENT2_MODEL"),
    model="gemini-2.5-flash",
    name="database_agent2",
    instruction=return_instructions_bigquery(),
    tools=[
        (
            #chase_db_tools.initial_bq_nl2sql
            tools.initial_bq2_nl2sql
            #if NL2SQL_METHOD == "CHASE"
            #else tools.initial_bq2_nl2sql
        ),
        tools.run_bigquery_validation,
    ],
    before_agent_callback=setup_before_agent_call,
    generate_content_config=types.GenerateContentConfig(temperature=1.0),  #(temperature=0.01)
)
