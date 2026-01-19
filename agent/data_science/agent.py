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

from datetime import date
from google.genai import types
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
import logging

# import os
# from google.adk.tools import load_artifacts

# ====================================================
# LiteLlm integration for HDFC Neev
# import litellm
# from google.adk.agents import LlmAgent
# from google.adk.models.lite_llm import LiteLlm
# ====================================================

from .sub_agents.bigquery.tools import (
    get_database_settings as get_bq_database_settings,
)
from .sub_agents.bigquery2.tools import (
    get_database2_settings as get_bq_database2_settings,
)
from .prompts import return_instructions_root
from .tools import call_db_agent, call_db_agent2, call_apptio_agent

date_today = date.today()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FinOps Agent initiated")

def setup_before_agent_call(callback_context: CallbackContext):
    """Setup the agent."""

    # setting up database settings in session.state
    if "database_settings" not in callback_context.state:
        db_settings = dict()
        db_settings["use_database"] = "BigQuery"
        callback_context.state["all_db_settings"] = db_settings
        callback_context.state["all_db_settings2"] = db_settings

    # setting up schema in instruction
    if callback_context.state["all_db_settings"]["use_database"] == "BigQuery":
        callback_context.state["database_settings"] = get_bq_database_settings()
        schema = callback_context.state["database_settings"]["bq_ddl_schema"]
        callback_context.state["database_settings2"] = get_bq_database2_settings()
        schema2 = callback_context.state["database_settings2"]["bq_ddl_schema2"]

        callback_context._invocation_context.agent.instruction = (
            return_instructions_root()
            + f"""

    --------- The BigQuery schema of the relevant data with a few sample rows. ---------
    {schema,schema2}

    """
        )


# FinOps Master Agent ( Root Agent )
root_agent = Agent(
    # model=os.getenv("ROOT_AGENT_MODEL"),
    model="gemini-2.5-flash",
    name="db_ds_multiagent",
    instruction=return_instructions_root(),
    global_instruction=(
        f"""
        You are a Data Science and Data Analytics Multi Agent System for Cloud FinOps.
        Todays date: {date_today}
        """
    ),
    tools=[
        call_db_agent,
        call_db_agent2,
        call_apptio_agent,
    ],
    before_agent_callback=setup_before_agent_call,
    generate_content_config=types.GenerateContentConfig(temperature=1.0),  #(temperature=0.01)
)