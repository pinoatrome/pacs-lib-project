from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Party:
    """A debtor or creditor, with its account: an IBAN, or another id such as a DEAN."""

    name: str | None = None
    iban: str | None = None
    other_id: str | None = None

    @property
    def account_id(self) -> str | None:
        return self.iban or self.other_id
