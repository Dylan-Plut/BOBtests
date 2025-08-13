# Slack + Cortex Agent (Python Bolt) Guide

This guide wires your Slack app to your custom Cortex Agent API with a polished Slack UI: slash command, modal, message shortcut, and App Home.

## What you get
- Slash command `/cortex` to open a modal or ask inline
- Message shortcut “Ask Cortex about this” for quick analysis
- App Home with a CTA button and tips
- Clean request to your Cortex Agent endpoint with optional context
- Optional Snowflake context scaffold

## 1) Configure credentials (required)
Set the following environment variables in your runtime (secrets manager, `.env`, or deployment config).

- SLACK_BOT_TOKEN=YOUR_SLACK_BOT_TOKEN
- SLACK_APP_TOKEN=YOUR_SLACK_APP_TOKEN
- CORTEX_AGENT_URL=YOUR_CORTEX_AGENT_ENDPOINT
- CORTEX_API_KEY=YOUR_CORTEX_API_KEY

Optional Snowflake (if your agent uses it):
- SNOWFLAKE_ACCOUNT=YOUR_ACCOUNT
- SNOWFLAKE_USER=YOUR_USER
- SNOWFLAKE_PASSWORD=YOUR_PASSWORD
- SNOWFLAKE_WAREHOUSE=YOUR_WAREHOUSE
- SNOWFLAKE_DATABASE=YOUR_DATABASE
- SNOWFLAKE_SCHEMA=YOUR_SCHEMA

Where to find/add in code:
- Add values in your environment before running `python3 app.py`.
- `app.py` reads `CORTEX_AGENT_URL` and `CORTEX_API_KEY` to authenticate calls.

## 2) Install dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Dependencies added:
- `requests` for Cortex API calls
- `snowflake-connector-python` for optional Snowflake integrations

## 3) Update Slack manifest
Open `manifest.json` and import it in Slack app config. This manifest includes:
- Slash command `/cortex`
- Message shortcut `Ask Cortex about this`
- App Home enabled
- Required bot scopes: `commands`, `chat:write`, `app_mentions:read`, `im:*`, `channels:history`, `users:read`

After updating the manifest in Slack, reinstall the app to your workspace.

## 4) Run locally (Socket Mode)
```bash
export SLACK_BOT_TOKEN=YOUR_SLACK_BOT_TOKEN
export SLACK_APP_TOKEN=YOUR_SLACK_APP_TOKEN
export CORTEX_AGENT_URL=https://your.cortex.endpoint/api/v1/agent/invoke
export CORTEX_API_KEY=YOUR_CORTEX_API_KEY
python3 app.py
```

The app uses Socket Mode, so no public URL is required for development.

## 5) Use the app
- Type `/cortex` in any channel, enter your question, optionally add context, and submit.
- Or open a message’s “More actions” and choose “Ask Cortex about this”.
- Check your App Home for a quick “Open Cortex” button.

## 6) What the Cortex API should return
`app.py` expects a JSON response like one of the following:
```json
{
  "answer": "Your answer as plain text"
}
```
```json
{
  "answer": "Summary",
  "blocks": [ { "type": "section", "text": { "type": "mrkdwn", "text": "Rich output" } } ]
}
```
```json
{
  "message": "Alternative key for plain text",
  "rich_text": "Rich formatted text (fallback if blocks absent)"
}
```
At minimum, return an `answer` or `message` string. If you provide `blocks` they will be posted directly.

The app sends this payload to your Cortex endpoint:
```json
{
  "question": "<user input>",
  "source": "slack",
  "metadata": {
    "slack_user_id": "U...",
    "slack_channel_id": "C..."
  },
  "context": "<optional additional context>"
}
```
Authentication: `Authorization: Bearer <CORTEX_API_KEY>`

## 7) Optional: Snowflake context
`app.py` contains `build_snowflake_context()` as a scaffold. If your agent needs Snowflake metadata, add it to the payload in `call_cortex_agent()` like:
```python
payload["snowflake"] = build_snowflake_context()
```
Provide or securely fetch any additional credentials your agent needs.

## 8) Production tips
- Store all secrets in a secure vault, not in code.
- Use Socket Mode for simplicity or deploy behind a secure public URL and switch to HTTP adapter.
- Add retry/backoff when calling Cortex; tune request timeout.
- Validate and sanitize user inputs server-side.

## 9) Troubleshooting
- Modal doesn’t open: ensure `commands` scope, reinstall app, verify Socket Mode enabled.
- 401 from Cortex: check `CORTEX_API_KEY` and that your endpoint authorizes the token.
- 404 on slash command: reinstall manifest and verify `/cortex` is present and enabled.
- No response DM: check logs; verify your event subscriptions and bot is in the conversation.

## File map
- `app.py`: Slack app, UI, and Cortex integration
- `manifest.json`: Slack app configuration
- `requirements.txt`: Python deps

Happy shipping!