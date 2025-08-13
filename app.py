import os
import json
import logging
from typing import Dict, Any, Optional

from dotenv import load_dotenv
import requests
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# Load environment from .env if present (local dev convenience)
load_dotenv()

# ---------- Configuration ----------
# Required environment variables (fill these in your runtime/.env)
# SLACK_BOT_TOKEN=***
# SLACK_APP_TOKEN=***
# CORTEX_AGENT_URL=https://your.cortex.endpoint/api/v1/agent/invoke
# CORTEX_API_KEY=***
# Optional Snowflake (if your agent or middleware uses it)
# SNOWFLAKE_ACCOUNT=***
# SNOWFLAKE_USER=***
# SNOWFLAKE_PASSWORD=***
# SNOWFLAKE_WAREHOUSE=***
# SNOWFLAKE_DATABASE=***
# SNOWFLAKE_SCHEMA=***
# Optional timeout
# CORTEX_TIMEOUT_SECONDS=60

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cortex_slack_app")

# Initializes your app with your bot token
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

CORTEX_AGENT_URL = os.environ.get("CORTEX_AGENT_URL")
CORTEX_API_KEY = os.environ.get("CORTEX_API_KEY")
CORTEX_TIMEOUT_SECONDS = int(os.environ.get("CORTEX_TIMEOUT_SECONDS", "60"))

# ---------- UI Helpers ----------

def build_cortex_modal(initial_query: str = "") -> Dict[str, Any]:
    return {
        "type": "modal",
        "callback_id": "cortex_modal_submit",
        "title": {"type": "plain_text", "text": "Cortex Agent"},
        "submit": {"type": "plain_text", "text": "Ask"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "query_block",
                "label": {"type": "plain_text", "text": "Question"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "query_input",
                    "placeholder": {"type": "plain_text", "text": "Ask your data assistant..."},
                    "initial_value": initial_query,
                    "multiline": True,
                },
            },
            {
                "type": "input",
                "optional": True,
                "block_id": "context_block",
                "label": {"type": "plain_text", "text": "Context (optional)"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "context_input",
                    "placeholder": {"type": "plain_text", "text": "Extra details, filters, or instructions"},
                    "multiline": True,
                },
            },
        ],
    }


def build_home_view() -> Dict[str, Any]:
    return {
        "type": "home",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Welcome to Cortex Agent for Slack. Use /cortex anywhere, or open the modal below to ask a question."
                },
            },
            {"type": "divider"},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Open Cortex"},
                        "action_id": "open_cortex_modal_from_home",
                        "style": "primary",
                    }
                ],
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Tip: Select any message and choose ‘Ask Cortex about this’ to analyze it."
                    }
                ],
            },
        ],
    }

# ---------- Cortex API Client ----------

def call_cortex_agent(question: str, *, context: Optional[str] = None, user_id: Optional[str] = None, channel_id: Optional[str] = None) -> Dict[str, Any]:
    if not CORTEX_AGENT_URL or not CORTEX_API_KEY:
        raise ValueError("CORTEX_AGENT_URL and CORTEX_API_KEY must be set in environment variables")

    headers = {
        "Authorization": f"Bearer {CORTEX_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload: Dict[str, Any] = {
        "question": question,
        "source": "slack",
        "metadata": {
            "slack_user_id": user_id,
            "slack_channel_id": channel_id,
        },
    }
    if context:
        payload["context"] = context

    logger.info("Calling Cortex Agent: %s", CORTEX_AGENT_URL)
    resp = requests.post(CORTEX_AGENT_URL, headers=headers, json=payload, timeout=CORTEX_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return resp.json()

# ---------- Snowflake Optional Helper (example) ----------

def build_snowflake_context() -> Dict[str, Any]:
    context: Dict[str, Any] = {}
    for key in [
        "SNOWFLAKE_ACCOUNT",
        "SNOWFLAKE_USER",
        "SNOWFLAKE_WAREHOUSE",
        "SNOWFLAKE_DATABASE",
        "SNOWFLAKE_SCHEMA",
    ]:
        val = os.environ.get(key)
        if val:
            context[key.lower()] = val
    return context

# ---------- Event Handlers ----------

@app.event("app_home_opened")
def update_home_tab(client, event, logger):
    try:
        client.views_publish(user=event["user"], view=build_home_view())
    except Exception as e:
        logger.exception("Failed to publish home: %s", e)


# Slash command: /cortex opens a modal
@app.command("/cortex")
def handle_cortex_command(ack, body, client, logger):
    ack()
    trigger_id = body.get("trigger_id")
    text = (body.get("text") or "").strip()

    modal = build_cortex_modal(initial_query=text)
    try:
        client.views_open(trigger_id=trigger_id, view=modal)
    except Exception as e:
        logger.exception("Failed to open Cortex modal: %s", e)


# Modal submission
@app.view("cortex_modal_submit")
def handle_modal_submission(ack, body, client, logger):
    state_values = body["view"]["state"]["values"]
    question = state_values["query_block"]["query_input"]["value"].strip()
    context = state_values.get("context_block", {}).get("context_input", {}).get("value")

    ack(response_action="clear")

    user_id = body.get("user", {}).get("id")

    try:
        result = call_cortex_agent(question, context=context, user_id=user_id)
        answer = result.get("answer") or result.get("message") or "No answer returned."
        rich = result.get("rich_text")
        blocks = result.get("blocks")

        # Open a DM with the user to deliver results
        dm = client.conversations_open(users=user_id)
        dm_channel = dm["channel"]["id"]

        if blocks and isinstance(blocks, list):
            client.chat_postMessage(channel=dm_channel, blocks=blocks, text=answer)
        else:
            text_out = answer if not rich else rich
            client.chat_postMessage(channel=dm_channel, text=text_out)

    except Exception as e:
        logger.exception("Cortex call failed: %s", e)
        try:
            dm = client.conversations_open(users=user_id)
            dm_channel = dm["channel"]["id"]
            client.chat_postMessage(channel=dm_channel, text=f"Sorry, I couldn't complete that request: {e}")
        except Exception:
            pass


# Message shortcut: analyze selected message
@app.shortcut("cortex_message_shortcut")
def handle_message_shortcut(ack, body, client, logger):
    ack()
    message_text = body.get("message", {}).get("text", "")
    trigger_id = body.get("trigger_id")
    modal = build_cortex_modal(initial_query=message_text)
    try:
        client.views_open(trigger_id=trigger_id, view=modal)
    except Exception as e:
        logger.exception("Failed to open modal from shortcut: %s", e)


# Friendly 'hello' example maintained
@app.message("hello")
def message_hello(message, say):
    say(
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"Hey there <@{message['user']}>! Ask me with /cortex"},
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Open Cortex"},
                    "action_id": "open_cortex_modal_from_message",
                    "style": "primary",
                },
            }
        ],
        text=f"Hey there <@{message['user']}>!",
    )


@app.action("open_cortex_modal_from_message")
def open_cortex_modal_from_message(ack, body, client, logger):
    ack()
    trigger_id = body.get("trigger_id")
    try:
        client.views_open(trigger_id=trigger_id, view=build_cortex_modal())
    except Exception as e:
        logger.exception("Failed to open Cortex modal from message action: %s", e)


@app.action("open_cortex_modal_from_home")
def open_cortex_modal_from_home(ack, body, client, logger):
    ack()
    trigger_id = body.get("trigger_id")
    try:
        client.views_open(trigger_id=trigger_id, view=build_cortex_modal())
    except Exception as e:
        logger.exception("Failed to open Cortex modal from home action: %s", e)


# Start your app
if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
