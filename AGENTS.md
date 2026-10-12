# Agent collaboration

This project is worked on from multiple computers and agent sessions. GitHub is the shared coordination point.

## Before each work session

- Read `CONTRIBUTING.md` and `docs/AGENT_HANDOFF.md`.
- Inspect the working tree and current branch, then fetch from `origin` before relying on local repository state.
- Compare the local branch with its remote counterpart. If the working tree is clean and the branch is only behind, update with a fast-forward. Preserve uncommitted work; never reset, discard changes, or force-push to resolve divergence.
- If remote access fails, explicitly report that synchronization could not be verified.

## After changes

- Update `docs/AGENT_HANDOFF.md` with a dated note describing the changes, checks and results, remaining work, and any limitations relevant to the next agent.
- Include the handoff note with the corresponding changes when committing and pushing. Check the remote again before publishing, since another session may have updated it meanwhile.
- Clearly report whether changes were pushed or remain local. Notes left only on one computer are not available to the other session.
- Keep notes concise and free of secrets, private paths, and client media.
