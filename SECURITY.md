# Security policy

This project is a local integration around a modified WeChat application. Keep
the OneBot and webhook ports bound to loopback, protect the generated token, and
never publish `data/`, `artifacts/`, `evidence/`, `backups/`, `downloads/`, or
runtime logs.

Please do not include account identifiers, message text, screenshots, tokens,
微信数据目录, or private crash dumps in a public issue. For a suspected
authentication, arbitrary-request, or data-disclosure problem, contact the
maintainer privately through the GitHub account hosting this repository before
opening a public issue.

The local OneBot cache and upstream runtime logs can contain message text,
chat identifiers, media metadata, and file paths. Treat them as private user
data: keep the runtime directory owner-only, redact them before sharing, and
remove local evidence before creating a public archive. The tracked patch
reduces request and response logging to byte counts, but it cannot protect
data already captured by an older runtime.

Frida Gadget currently listens on `127.0.0.1:27042` without connection
authentication. A local process that can connect may instrument WeChat without
the OneBot token. Loopback binding does not isolate local users or applications.
Do not forward this port. Gadget authentication must be configured together
with both the OneBot and native-send clients before this boundary is hardened.

MCP clients are trusted: any connected client can read the captured cache and
invoke message sending. The server's instruction to send only user-authorized
messages is guidance for the client, not an enforced per-message approval gate.
SQLite caches are not encrypted by this project. Their access is controlled by
local filesystem permissions; root and processes running as the same user are
outside that protection.

The project does not promise compatibility or safety for an unlisted WeChat
Build. A report should include the macOS version, CPU architecture, project
commit, and exact WeChat Build, but should omit personal data.
