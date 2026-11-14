"""Module Juridique - Q&R et documents juridiques.

Ce package expose les fonctions publiques suivantes :
- ``logic`` : logique RAG paramétrée par ``shared.qr_config.QRModuleConfig``
- ``view`` : vue Streamlit Q&R et déclaration spécifique
"""

from . import logic, view  # noqa: F401