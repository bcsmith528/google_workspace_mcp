# Citadel build of google_workspace_mcp

Branch `citadel/v1.22.0-drafts` = upstream tag `v1.22.0` plus two Gmail tools:

- `list_gmail_drafts`: lists drafts with their Draft IDs (search tools only return Message IDs, which `drafts.*` rejects).
- `update_gmail_draft`: revises a draft in place. Omitted subject/To/Cc/Bcc/From and reply threading are carried forward; the body is replaced; a draft with attachments is only updated if they are re-passed or `drop_existing_attachments=true`.

No delete tool on purpose: `drafts.delete` bypasses Trash.

Threading fix (`1.22.0-drafts3`, 2026-10-05): reply drafts now land inside their thread. Two changes in `gmail/gmail_tools.py`:

- Messages serialize with `max_line_length=998` (RFC 5322) instead of SMTP's 78. At 78, Python RFC 2047-encoded any Message-ID longer than a line (Outlook IDs always are), so `In-Reply-To`/`References` stopped matching and Gmail filed the reply as a new conversation.
- `draft_gmail_message` and `update_gmail_draft` set `message.threadId` again when reply headers are present. Upstream removed it for #845 (drafts hidden in the Gmail UI); those reports had the mangled headers too. With intact headers, verified live: the draft sits in the thread and shows in Drafts and Inbox.

Both instances on CT210 run it: `gws-mcp-lan` (`/opt/gws-lan`, Claude Code + Jarvis) and `gws-mcp` (`/home/ubuntu/gws-mcp`, claude.ai connectors). Scope needed is `gmail.compose`, which all four stored accounts already have.

## Build and deploy (on CT210)

```
cd /opt/gws-drafts-build            # this repo's Dockerfile.citadel, gmail/gmail_tools.py, core/tool_tiers.yaml
docker build -f Dockerfile.citadel -t gws-mcp-citadel:<tag> .    # running: 1.22.0-drafts3
# set image: gws-mcp-citadel:<tag> in both compose files, then:
cd /opt/gws-lan && docker compose up -d
cd /home/ubuntu/gws-mcp && docker compose -p gwsmcp -f docker-compose.ct.yml up -d
```

The public instance's directory also holds an old `docker-compose.yml` from a retired host. A plain `docker compose up` there reads that file, so always pass `-p gwsmcp -f docker-compose.ct.yml`.

## Two OAuth clients, not interchangeable

- `gws-mcp` (OAuth 2.1 proxy) uses the **web** client, the one whose redirect URI is this instance's `/oauth2callback`. Its ID and secret come from `/home/ubuntu/gws-mcp/.env`, which compose reads.
- `gws-mcp-lan` uses the **desktop** client that issued the refresh tokens in `/opt/gws-lan/creds`.

Every upstream refresh token the proxy stores belongs to the web client. Start `gws-mcp` with the desktop client and it keeps working until each connection's next token renewal. Then Google answers `unauthorized_client`, and every claude.ai connector drops to Reconnect. That happened on 2026-10-05: the switch to compose read a `.env` left over from August, while the container it replaced had been started by hand with the web client. Before recreating `gws-mcp`, check that the client ID in `.env` is the web client.

## Rollback

Set both compose files back to
`ghcr.io/taylorwilsdon/google_workspace_mcp@sha256:4841e2b635a0e29cbe58472e69dc0b0bc1caa69b90834f51106c843763156837`
and run the same two `up -d` commands.

## Upgrading upstream

Upstream (v2.0.1 as of 2026-10-05) still has no draft update. Before moving to a newer upstream image, rebase this branch onto the new tag or check whether one of the open draft PRs (#1035, #812, #781) merged; otherwise the upgrade silently removes these tools.
