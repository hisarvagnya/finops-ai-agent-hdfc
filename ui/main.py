from flask import Flask, request, jsonify, render_template, Response
from flask_cors import CORS
import googleapiclient.discovery
import logging
from google.cloud import logging as cloud_logging
import json
from vertexai import agent_engines
import os
#from config import REASONING_ENGINE_URI, user_email
from config import REASONING_ENGINE_URI
from google.api_core import exceptions as google_exceptions

import vertexai 

from asgiref.wsgi import WsgiToAsgi

################ Revision Historty ################
#Last Updated : 21/09
#Updated By : Sarvagnya A ; Harshapriya
#Comment :
###################################################


logging_client = cloud_logging.Client()
logging_client.setup_logging()

log_name = "HDFC Cloud Run Agent"
custom_logger = logging.getLogger(log_name)


# Flask App Initialization
app = Flask(__name__)
CORS(app)

# --- Frontend Route ---
@app.route('/')
def index():
    return render_template('index.html')

# --- Route for sample prompts---
@app.route('/prompts.html')
def prompts():
    return render_template('prompts.html')

# --- Backend API Route ---
@app.route('/api/agent', methods=['POST', 'OPTIONS'])
async def agent_handler():
    if request.method == 'OPTIONS':
        return Response(status=204, headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Authorization, Content-Type',
            'Access-Control-Max-Age': '3600'
        })

    try:
        # 0. Extract User email from IAP : 18Dec
        iap_user_email_header = request.headers.get('X-Goog-Authenticated-User-Email')
        if not iap_user_email_header:
            custom_logger.error("IAP header missing. Access may be unauthenticated.")
            # For security, you should deny access if this header is missing.
            return jsonify({"error": "Unauthorized: IAP header missing."}), 401
        
        # Strip the "accounts.google.com:" prefix to get the clean email.
        authenticated_user_id = iap_user_email_header.split(':')[-1]
        custom_logger.info(f"DEBUG: Authenticated user: {authenticated_user_id}")

        # --- END IAP USER EMAIL EXTRACTION ---
        
        # 1. Get Request Data (This is fine)
        request_json = request.get_json()
        if not request_json:
            return jsonify({"error": "Bad Request: Missing or invalid JSON body."}), 400

        prompt = request_json.get('prompt')
        session_id_from_client = request_json.get('session_id') 
        custom_logger.info(f"DEBUG: Received prompt: {prompt}, session_id: {session_id_from_client}")
        
        if not prompt:
            return jsonify({"error": "Bad Request: Missing 'prompt' key in JSON."}), 400
        
        
        custom_logger.info("Initializing Vertex AI Client and Agent Engine (Global)...")
        project_id = "hbl-gcp-prod-finops-prj-spk-d1"
        location = "asia-south1"
        
        # 1. Create the client (once)
        client = vertexai.Client(project=project_id, location=location)
        
        # 2. Get the deployed agent (once)
        adk_app = client.agent_engines.get(name=REASONING_ENGINE_URI)
        
        custom_logger.info("Agent Engine client initialized globally.")

        # # 2. Handle the Session (Using the GLOBAL adk_app)
        # if not session_id_from_client:
        #     custom_logger.info(f"Creating new session for user: {user_email}")
        #     new_session_object = await adk_app.async_create_session(user_id=user_email)
        #     session_id_to_use = new_session_object["id"]
        #     custom_logger.info(f"session created is: {session_id_to_use}")
        # else:
        #     custom_logger.info(f"Using existing session: {session_id_from_client}")
        #     session_id_to_use = session_id_from_client
        
        # 2. Handle the Session (Using the GLOBAL adk_app) : 18Dec
        if not session_id_from_client:
            custom_logger.info(f"Creating new session for user: {authenticated_user_id}")
            new_session_object = await adk_app.async_create_session(user_id=authenticated_user_id)
            session_id_to_use = new_session_object["id"]
            custom_logger.info(f"session created is: {session_id_to_use}")
        else:
            custom_logger.info(f"Using existing session: {session_id_from_client}")
            session_id_to_use = session_id_from_client

        # 3. Process the Stream
        final_answer = ""
        
        async for event in adk_app.async_stream_query(
            #user_id=user_email, 18Dec
            user_id=authenticated_user_id,
            session_id=session_id_to_use,  
            message=prompt,
        ):
            
            custom_logger.info(f"DEBUG: Agent event: {event}")

            if isinstance(event, dict):
                if 'content' in event:
                    for part in event.get('content', {}).get('parts', []):
                        if 'text' in part:
                            final_answer += part['text']
                
                elif 'error' in event or event.get('type') == 'ERROR':
                    custom_logger.error(f"FATAL: Received ERROR event: {event}")
                    final_answer = "Error: Agent Stream returned an explicit error."
                    break  
                
        # 4. Return the FINAL response
        if not final_answer:
            custom_logger.warning("Stream finished but no final_answer was captured.")
            final_answer = "Sorry, I couldn't get a conclusive response."
                
        final_payload = {"response": final_answer, "session_id": session_id_to_use}
        custom_logger.info(f"DEBUG: Sending final payload to client: {json.dumps(final_payload)}")
        return jsonify(final_payload)


    except Exception as e:
            custom_logger.exception("Internal server error in /api/agent: %s", e)
            return jsonify({"error": "Internal Server Error.", "details": str(e)}), 500

#if __name__ == '__main__':
    #var = "Test"
    # This is for local development only
    #app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

#29Sep UI Fix
application = WsgiToAsgi(app)