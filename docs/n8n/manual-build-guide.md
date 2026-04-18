# Legal AI n8n Manual Build Guide

Build these workflows directly in the n8n editor. No file import is required.

## WhatsApp provider choice

- Use WhatsApp Business Cloud API for the client-facing WhatsApp number.
- The sending number is the WhatsApp Business number connected to Meta, not a personal WhatsApp app account.
- If you send the first consent message outside the 24-hour customer-service window, use an approved template message.
- If the 24-hour window is already open, a normal text message is allowed.
- For the consent step, the simplest n8n setup is the WhatsApp Business Cloud node with "Send and Wait for Response" and Approval buttons.
- If you prefer typed reply handling, you can still use a webhook-based flow, but the approval-button version is easier and more reliable.

## Workflow 1: Call orchestration

### 1) Add the trigger
- Add a `Webhook` node.
- Set `HTTP Method` to `POST`.
- Set `Path` to `legal-ai/call-events`.
- Set `Authentication` to `None`.
- Keep `Respond` set to `Using Respond to Webhook Node`.

### 2) Add the router
- Add a `Switch` node after the webhook.
- Route on `event_type`.
- Add three outputs:
  - `consent.request`
  - `consent.reply.received`
  - `transcription.completed`

### 3) Consent request branch
- Add a `Code` node.
- Build these values from the incoming JSON:
  - `backendBaseUrl`
  - `backendCallbackUrl`
  - `whatsappTo`
  - `consentMessage`
- Add a `WhatsApp Business Cloud` node.
- Use the `Message` operation.
- Use `Send and Wait for Response`.
- Set the response type to `Approval`.
- Label the approval button `Yes`.
- Label the disapproval button `No`.
- Put the consent text in the message body.
- Add an `HTTP Request` node after the WhatsApp node to notify the backend that consent was accepted or rejected.
- On acceptance, continue the workflow to the call-start branch.
- On rejection, stop the workflow after notifying the backend.
- End each path with `Respond to Webhook`.

### 4) Consent reply branch
- Add a `Code` node.
- Normalize the reply text to lower case.
- Mark it accepted when the reply is `yes`, `y`, `ok`, `okay`, or `oui`.
- Add an `IF` node.
- If accepted, notify the backend and then call your provider to start the call.
- If rejected, notify the backend that consent was not accepted.
- End with `Respond to Webhook`.

### 5) Transcript branch
- Add an `HTTP Request` node.
- POST the transcript payload to the backend webhook.
- Include:
  - `event_type: transcription.completed`
  - `call_session_id`
  - `voice_recording_id`
  - `transcript_text`
  - `transcript_source`
  - `transcript_language`
  - `conversation_turns`
- End with `Respond to Webhook`.

## Recommended simpler variant

If you want the least moving parts, use the WhatsApp Business Cloud node for the consent message and response handling, then keep only the transcript branch as an HTTP callback back into the backend.

That means:

1. Your app creates the call session.
2. n8n sends the WhatsApp consent message.
3. n8n waits for the approval button response.
4. If approved, n8n tells the backend the call can proceed.
5. If rejected, n8n stops.
6. After the call, your transcription model stores the conversation transcript in the backend.

## Workflow 2: Inbound WhatsApp replies

### 1) Add the trigger
- Add a second `Webhook` node.
- Set `HTTP Method` to `POST`.
- Set `Path` to `legal-ai/whatsapp/inbound`.

### 1a) Optional verification workflow for Meta
- If you connect Meta webhooks directly instead of using the n8n WhatsApp node, create a second Webhook path for the `GET` verification request.
- Validate `hub.verify_token` and echo `hub.challenge` back.
- Meta requires the webhook endpoint to pass this verification before it can receive message events.

### 2) Normalize the provider payload
- Add a `Code` node.
- Extract:
  - `text` or `body` into `body`
  - sender phone into `from_phone`
  - recipient/client phone into `client_phone`
  - `call_session_id` from metadata
  - `message_id`

### 3) Forward to the backend
- Add an `HTTP Request` node.
- POST to `{{LEGAL_AI_BACKEND_URL}}/integrations/n8n/events`.
- Send:
  - `event_type: consent.reply.received`
  - `call_session_id`
  - `body`
  - `client_phone`
  - `caller_phone`
  - `consent_message`
- Add a `Respond to Webhook` node.

### 4) Important note about Meta replies
- Meta does not always hand back your internal call session id on the reply webhook.
- If you use this direct webhook variant, match the reply to the latest pending consent session by client phone number in your backend or with an extra lookup step.

## Environment variables

Set these in the n8n container:

- `LEGAL_AI_BACKEND_URL`
- `N8N_WEBHOOK_SECRET`
- `WHATSAPP_SEND_ENDPOINT`
- `WHATSAPP_SEND_AUTH_TOKEN`
- `WHATSAPP_CALL_START_ENDPOINT`
- `WHATSAPP_CALL_START_AUTH_TOKEN`
- `META_WHATSAPP_ACCESS_TOKEN`
- `META_WHATSAPP_PHONE_NUMBER_ID`
- `META_WHATSAPP_VERIFY_TOKEN`

## Where to see the workflow

- The workflow appears on the canvas as soon as you add the nodes.
- After you click Save, it shows in your n8n workspace list.
- Use the `Personal` workspace and the editor page you already opened.

## Recommended order

1. Build Workflow 1.
2. Save it.
3. Build Workflow 2.
4. Save it.
5. Activate both workflows.
