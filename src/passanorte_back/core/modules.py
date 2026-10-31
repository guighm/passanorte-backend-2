"""Lista canônica dos 10 módulos de domínio (constituição, decisão fundacional).

Única fonte de verdade para registro de routers e verificação de fronteiras.
"""

from typing import Final

DOMAIN_MODULES: Final[tuple[str, ...]] = (
    "auth",
    "funcionarios",
    "turistas",
    "pontos_turisticos",
    "eventos",
    "gamificacao",
    "visitacao",
    "dashboard",
    "notificacoes",
    "chatbot",
)
