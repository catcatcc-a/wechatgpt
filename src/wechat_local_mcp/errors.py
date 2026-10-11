"""Explicit send-state failures shared by backend adapters and the MCP bridge."""


class SendNotAttempted(RuntimeError):
    """The backend can establish that no send action was attempted.

    Use this only before dispatching/clicking Send. Failures after dispatch or
    interrupted actions must remain ordinary exceptions with unknown outcomes.
    """
