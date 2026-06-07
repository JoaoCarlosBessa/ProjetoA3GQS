# conftest.py
# Configurações globais compartilhadas entre todos os testes.
# O pytest carrega este arquivo automaticamente.

import pytest


def pytest_configure(config):
    """Registra marcadores customizados para organização dos testes."""
    config.addinivalue_line("markers", "unit: testes unitários — funções isoladas")
    config.addinivalue_line("markers", "integration: testes de integração — funções + banco de dados")
    config.addinivalue_line("markers", "system: testes de sistema — fluxos completos de ponta a ponta")
