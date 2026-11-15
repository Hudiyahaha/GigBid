# ADR 0003: Approval enforced in the graph AND in the tool server
**Decision:** besides the LangGraph `interrupt()`, every marketplace write needs an HMAC token minted by the API on human
approval, bound to the exact payload. **Why:** a bug, a prompt injection or a future agent cannot bypass the human,
because the tool server itself refuses. **Cost:** one extra parameter on write tools.
