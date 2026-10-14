# Kollino Restaurant

Public distribution of Kollino Restaurant for ChatGPT, Codex and Claude. Packages are generated from reviewed private Merchant sources. This Git marketplace is separate from approval and listing in the platforms' official directories.

The plugin reads authorized menus and service hours, prepares menu proposals for customer review, follows import status and reads anonymous upsell statistics. It does not perform payments, publish menus directly, publish advertisements or expose internal administration.

OpenAI packages use central reviewed guidance from the restaurant MCP profile. Claude packages bundle reviewed workflow snapshots. Both use authorization-code OAuth with S256 PKCE and resource-bound consent. Use the resource URL recorded in the release manifest; reconnect after the migration from the old API paths.

For Claude Code, add this marketplace with `claude plugin marketplace add Kollino-se/ai-plugins`, then install `kollino-restaurant@kollino`. For Codex/ChatGPT desktop, use the repository marketplace in the cloned distribution repository. For reproducible installation and review, use the exact release tag or commit rather than an unpinned branch. Platform portal acceptance must be verified separately.

Release packages and SHA256SUMS are attached to GitHub releases. The public workflows validate and reproduce exported archives without access to private Merchant code. Package versions are immutable. Metadata and bundled workflow changes require a new version. Compatible hosted OpenAI guidance follows the server's separate release lifecycle.

Licensing: code and manifests use Apache-2.0; Markdown guidance uses CC BY 4.0. Brand assets are excluded from those grants. See LICENSE and LICENSES.md. The referenced brand policy still requires publisher completion.

Submission readiness also requires verified product/support/privacy/terms URLs, publisher identity, demo recording, countries/languages/commerce declarations, reviewer access, client behavior evidence and portal verification. A GitHub release does not establish those requirements.
