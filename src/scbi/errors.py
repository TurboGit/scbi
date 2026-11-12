"""Exceptions shared by the driver modules."""


class Exit(Exception):
    """Stop the driver with an exit status."""

    def __init__(self, status: int):
        super().__init__(status)
        self.status = status


class NotImplementedYet(Exception):
    """A feature of the Bash driver not ported yet."""
