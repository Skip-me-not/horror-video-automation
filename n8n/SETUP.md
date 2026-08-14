# n8n setup

1. In n8n, import `horror-video-orchestrator.json`.
2. Create a fine-grained GitHub token limited to `Skip-me-not/horror-video-automation`.
   Grant **Actions: Read and write** and **Metadata: Read**. In n8n, store it as
   a Header Auth credential: header `Authorization`, value `Bearer TOKEN`.
3. Select that credential on both **Dispatch Scheduled Story** and
   **Dispatch GitHub Workflow**. The credential ID in the export is intentionally
   a placeholder.
4. The repository and branch are already set to `Skip-me-not/horror-video-automation`
   and `main`. In **Construct Job**, replace only the callback URL with the
   production URL shown by **GitHub Result Callback**.
5. Open **Daily Schedule** to review the default times: `05:30`, `08:30`,
   `11:30`, and `14:30`. The workflow timezone is `Asia/Yangon`, so these are
   Myanmar local times. Edit the cron expression if different times are needed.
6. Test **Dispatch Scheduled Story** once. A successful GitHub dispatch returns
   HTTP 204. Also test **Manual Trigger**; its demo expects
    `assets/backgrounds/dark-corridor.png`. Add licensed ambience later if desired.
7. Publish/activate the n8n workflow. Schedule Trigger only fires while the
   workflow is active. GitHub's own cron is intentionally disabled, preventing
   duplicate uploads. Scheduled dispatches leave `idea_number` empty so GitHub
   rotates automatically through the 500-story bank.
8. Send optional prepared stories as JSON with `POST` to the
    production URL shown by **Prepared Story Webhook**. Stories must be original
    English text between 180 and 1100 characters. Narration determines the
    final 24-59 second duration.
9. Optionally configure Telegram credentials/chat ID, then enable the disabled
   Telegram node. It is not needed for the callback or upload.

GitHub returns HTTP 204 when the dispatch is accepted. The eventual result
arrives independently at the callback webhook. Do not put GitHub, Google, or
Telegram tokens in Code nodes or exported JSON.
