# n8n Workflows for Legal AI

## Start here

- If you want to build the workflow manually in n8n, follow [manual-build-guide.md](manual-build-guide.md).
- If you want the repo artifacts, the export files are still available in this folder.

## Files

- [manual-build-guide.md](manual-build-guide.md): node-by-node manual setup.
- [legal-ai-call-orchestration.workflow.json](legal-ai-call-orchestration.workflow.json): starter export for consent request, consent reply, and transcription routing.
- [legal-ai-whatsapp-inbound.workflow.json](legal-ai-whatsapp-inbound.workflow.json): starter export for inbound WhatsApp reply forwarding.

## Environment variables

Set these in the n8n container or host environment:

- `LEGAL_AI_BACKEND_URL`
- `N8N_WEBHOOK_SECRET`
- `WHATSAPP_SEND_ENDPOINT`
- `WHATSAPP_SEND_AUTH_TOKEN`
- `WHATSAPP_CALL_START_ENDPOINT`
- `WHATSAPP_CALL_START_AUTH_TOKEN`
- `META_WHATSAPP_ACCESS_TOKEN`
- `META_WHATSAPP_PHONE_NUMBER_ID`
- `META_WHATSAPP_VERIFY_TOKEN`

## WhatsApp Business Cloud API

- Use the WhatsApp Business Cloud number connected to Meta as the sending number.
- Use an approved template for the first outbound consent message if the customer-service window is closed.
- If you want the simplest path, use the n8n WhatsApp Business Cloud node with `Send and Wait for Response` and `Approval`.
- If you want to receive raw Meta webhook replies, add the optional verification and inbound webhook flow described in the manual build guide.

## Where to see it in n8n

- As soon as you add nodes, they appear on the editor canvas.
- After saving, the workflow shows up in the left-side workflow list under your personal workspace.
- You can also find it from the main n8n overview/workflows pages after saving.

## What each workflow does

- `legal-ai-call-orchestration.workflow.json` sends the consent request, notifies the backend, handles acceptance or rejection, and forwards transcript updates.
- `legal-ai-whatsapp-inbound.workflow.json` receives inbound WhatsApp replies from your provider and forwards them to the backend as consent replies.
