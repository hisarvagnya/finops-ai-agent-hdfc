import os
import logging
import urllib3

import litellm
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

# ==================================================
# Logging
# ==================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("finops-agent")

# ==================================================
# DEV ONLY: Disable SSL verification
# ==================================================
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
litellm.ssl_verify = False

# ==================================================
# FORCE OPENAI TRANSPORT (CRITICAL)
# ==================================================
litellm.custom_llm_provider = "openai" 
litellm.drop_params = True
litellm.set_verbose = False

# ==================================================
# OpenAI-Compatible Config
# ==================================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "sk-IOkU-X0hokhgwDDSvYjqGg")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://genai-proxy-prod.hbctxdom.com/PROD/litellm")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gemini-2.5-flash")

litellm.api_key = OPENAI_API_KEY
litellm.api_base = OPENAI_BASE_URL

logger.info("OPENAI_BASE_URL=%s", OPENAI_BASE_URL)
logger.info("OPENAI_MODEL=%s", OPENAI_MODEL)

# ==================================================
# Agent initial Setup
# ==================================================
def setup_before_agent_call(callback_context):
    """Setup the agent."""
    litellm.custom_llm_provider = "openai" 
    litellm.drop_params = True
    litellm.set_verbose = False
    litellm.api_key = 'sk-IOkU-X0hokhgwDDSvYjqGg'
    litellm.api_base = 'https://genai-proxy-prod.hbctxdom.com/PROD/litellm'


# ==================================================
# Root Agent
# ==================================================
root_agent = LlmAgent(
    name="finops_sample_agent",
    instruction=(
        "You are a Cloud FinOps Agent. "
        "You help with cloud cost optimization, "
        "usage analysis, and financial governance."
    ),
    model=LiteLlm(
        model=OPENAI_MODEL,            # EXACT name preserved
        provider="openai",             # required by ADK
        custom_llm_provider="openai",  # defeats heuristics
    ),
    before_agent_callback=setup_before_agent_call,
)


# ==================================================
# ADK ENTRYPOINT
# ==================================================
def get_agent() -> LlmAgent:
    return root_agent