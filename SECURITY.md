# Security policy

This project is a local integration around a modified WeChat application. Keep
the OneBot and webhook ports bound to loopback, protect the generated token, and
never publish `data/`, `artifacts/`, `evidence/`, `backups/`, `downloads/`, or
runtime logs.

Please do not include account identifiers, message text, screenshots, tokens,
微信数据目录, or private crash dumps in a public issue. For a suspected
authentication, arbitrary-request, or data-disclosure problem, contact the
maintainer privately before opening a public issue. This repository is still a
local source preview: before public launch, the owner must enable GitHub private
vulnerability reporting or provide a verified private contact. Once enabled,
use Security → Report a vulnerability. Do not put security details in a public
issue when no private channel is available.

The local OneBot cache and upstream runtime logs can contain message text,
chat identifiers, media metadata, and file paths. Treat them as private user
data: keep the runtime directory owner-only, redact them before sharing, and
remove local evidence before creating a public archive. The tracked patch
reduces request and response logging to byte counts, but it cannot protect
data already captured by an older runtime.

Frida Gadget uses an independent random token on `127.0.0.1:27042`. The token
file and the configuration inside the modified app must both be owner-only
(`0600`); both clients reject missing credentials. Do not share the modified
app bundle: it contains this private token. Existing installations require a
coordinated app/client upgrade and a WeChat restart to enable authentication.
Loopback binding and token authentication do not isolate root or processes
that can read files as the same macOS user. Do not forward this port.

The patch permits only selected numeric metrics and error types in structured
logs, suppresses raw JS logs and media dumps, and limits HTTP/WS message sizes
and network timeouts. Builds pin Go 1.26.9. See the current implementation,
validation and deployment state in [security remediation](docs/security-remediation.md).

MCP clients are trusted: any connected client can read the captured cache and
invoke message sending. The server's instruction to send only user-authorized
messages is guidance for the client, not an enforced per-message approval gate.
SQLite caches are not encrypted by this project. Their access is controlled by
local filesystem permissions; root and processes running as the same user are
outside that protection.

The project does not promise compatibility or safety for an unlisted WeChat
Build. A report should include the macOS version, CPU architecture, project
commit, and exact WeChat Build, but should omit personal data.
