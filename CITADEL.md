# Citadel build of google_workspace_mcp

Branch `citadel/v1.22.0-drafts` = upstream tag `v1.22.0` plus two Gmail tools:

- `list_gmail_drafts`: lists drafts with their Draft IDs (search tools only return Message IDs, which `drafts.*` rejects).
- `update_gmail_draft`: revises a draft in place. Omitted subject/To/Cc/Bcc/From and reply threading are carried forward; the body is replaced; a draft with attachments is only updated if they are re-passed or `drop_existing_attachments=true`.

No delete tool on purpose: `drafts.delete` bypasses Trash.

Both instances on CT210 run it: `gws-mcp-lan` (`/opt/gws-lan`, Claude Code + Jarvis) and `gws-mcp` (`/home/ubuntu/gws-mcp`, claude.ai connectors). Scope needed is `gmail.compose`, which all four stored accounts already have.

## Build and deploy (on CT210)

```
cd /opt/gws-drafts-build            # this repo's Dockerfile.citadel, gmail/gmail_tools.py, core/tool_tiers.yaml
docker build -f Dockerfile.citadel -t gws-mcp-citadel:1.22.0-drafts1 .
# set image: gws-mcp-citadel:1.22.0-drafts1 in both compose files, then in each dir:
docker compose up -d
```

## Rollback

Set both compose files back to
`ghcr.io/taylorwilsdon/google_workspace_mcp@sha256:4841e2b635a0e29cbe58472e69dc0b0bc1caa69b90834f51106c843763156837`
and `docker compose up -d`.

## Upgrading upstream

Upstream (v2.0.1 as of 2026-10-05) still has no draft update. Before moving to a newer upstream image, rebase this branch onto the new tag or check whether one of the open draft PRs (#1035, #812, #781) merged; otherwise the upgrade silently removes these tools.
