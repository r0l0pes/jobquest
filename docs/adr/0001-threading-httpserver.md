# 0001 — Switch to ThreadingHTTPServer for concurrent request handling

**Status:** accepted

The tracker server (`serve_tracker.py`) needs to handle concurrent requests: when a long-running discovery subprocess is executing (up to 180s), the user must still be able to poll progress endpoints, load the tracker page, and load the pipeline page. The initial implementation used `HTTPServer` (single-threaded), which blocks all requests during long handlers.

Switched to `ThreadingHTTPServer` — a one-line change from Python's stdlib (`socketserver.ThreadingMixIn`). This creates a new thread per request, allowing concurrent handling of discovery polling, progress log reads, and page loads while the discovery subprocess runs.

**Considered options:**
- **Keep single-threaded + async subprocess**: More complex, requires non-blocking I/O and a custom event loop. No advantage over threading for this use case.
- **Fork a separate status server**: Adds another port, process management overhead. Unnecessary complexity.
- **ThreadingHTTPServer (chosen)**: Simplest change, pure stdlib, well-tested, well-understood pattern. The tracker server is internal-only (localhost), so threading overhead is irrelevant.

**Consequences:**
- The server now handles requests concurrently — a slow endpoint won't block others.
- Thread safety: shared state (the discovery process registry) uses a `threading.Lock`.
- No external dependencies.
