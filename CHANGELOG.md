# Changelog

All notable changes to this project will be documented in this file.

The format is inspired by Keep a Changelog and Semantic Versioning.

## [0.2.0] - 2025-11-13
### Added
- Admin UI overhaul with clearer layout, dark theme, and inline explanations.
- Assistant management: sync current function tools to OpenAI; view assistant info.
- MCP management: configure servers/token; test MCP via list-tools; example MCP server.
- Config export/import endpoints and UI to snapshot and restore configuration.
- Configurable assistant instructions (`ASSISTANT_INSTRUCTIONS`).
- Tool enablement via `ENABLED_TOOLS` with filtering in tool schemas.
- CI workflow (GitHub Actions): smoke test `/health` and Docker build.

### Changed
- Twilio webhook now returns `204 No Content` to avoid stray "OK" message in WhatsApp.
- Admin page explains sandbox vs real WhatsApp numbers, signature validation, and tool usage.

### Fixed
- JS sandbox driver string construction (avoid f-string syntax issues) and small stability tweaks.

## [0.1.0] - 2025-11-13
### Added
- Initial release: FastAPI server with Twilio WhatsApp webhook and OpenAI integration.
- Tools: code execution (Python/JS), HTTP client with allowlist, MCP thin client, and safe system tools.
- Session store, conversation engine, and command parser.
- Health endpoint, logging, Dockerfile, and documentation.

[0.2.0]: https://github.com/yishaik/wotbot/releases/tag/v0.2.0
[0.1.0]: https://github.com/yishaik/wotbot/releases/tag/v0.1.0
