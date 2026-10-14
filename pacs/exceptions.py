class PacsError(Exception):
    """A pacs message can't be built or read."""


class PacsParseError(PacsError):
    """The XML isn't a readable message of the expected kind."""
