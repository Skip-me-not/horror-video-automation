# n8n setup

1. In n8n Cloud, import `horror-video-orchestrator.json`.
2. Create a fine-grained GitHub token limited to the target private repository.
   Grant **Actions: Read and write** and **Metadata: Read**. In n8n, store it as
   a Header Auth credential: header `Authorization`, value `Bearer TOKEN`.
3. Open **Dispatch GitHub Workflow** and select that credential. The credential
   ID in the export is intentionally a placeholder.
4. Edit the four values in **Construct Job**: repository owner, repository name,
   branch, and the production URL shown by **GitHub Result Callback**.
5. Test with **Manual Trigger**. The demo expects
    `assets/backgrounds/dark-corridor.png`. Add licensed ambience later if desired.
6. Activate the workflow. Send prepared stories as JSON with `POST` to the
    production URL shown by **Prepared Story Webhook**. Stories must be original
    English text between 220 and 2200 characters. Narration determines the
    final duration, up to 179 seconds.
7. Optionally configure Telegram credentials/chat ID, then enable the disabled
   Telegram node. It is not needed for the callback or upload.

GitHub returns HTTP 204 when the dispatch is accepted. The eventual result
arrives independently at the callback webhook. Do not put GitHub, Google, or
Telegram tokens in Code nodes or exported JSON.
