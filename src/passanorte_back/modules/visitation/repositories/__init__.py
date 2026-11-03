"""Repositories of the visitation module (private layer — never imported
outside the module; the ledger's consumers go through public services)."""

from passanorte_back.modules.visitation.repositories.visitations import Visitation

__all__ = ["Visitation"]
