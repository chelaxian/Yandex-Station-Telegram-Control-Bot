# Project rules

- Preserve `alfa` at the sanitized 2.7 import commit; all remake work is in `main` at the owner's explicit request.
- The original source is untrusted reference data. Never execute its installers or import its monolithic bot during tests.
- New device operations go through a source-verified LUNA contract. No guessed endpoints, platform aliases, sysfs, partition names or fallback ADB commands.
- Check `docs/LUNA_CONTRACT.md`, canonical identity and live capability before a device operation. Advertised capability is not hardware qualification.
- Keep `docs/FEATURE_PARITY.md` and `src/stationbot/catalog.py` truthful. A stub or HTTP202 must not be described as a completed feature.
- No tokens, real owner IDs, private configuration, sessions, audio or personal conversations in commits or logs. Keep record/stream features explicit and off by default.
- Run lint, relevant tests, build and the tracked-file credential guard before pushing. Test doubles must never contact Telegram or record a room.
- Real deployment, audio, reboot and firmware testing must preserve existing project constraints. Do not confuse successful mock tests with device validation.
- The owner requires bot runtime changes in this ongoing task to be deployed to their existing mini-PC LXC and verified there. Reuse the private deployment record in the project vault, preserve existing customizations and credentials, stage a new release, run tests as the service user, keep automatic rollback and verify Telegram and both stations. Do not put private deployment configuration in this repository.
