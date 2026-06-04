"""
BaseAgent — clase base para todos los agentes especializados de ORBYT LAND.

Características:
- Prompt caching en system prompt (tokens cacheados = 90% de descuento)
- Routing de texto: cada agente recibe solo las secciones relevantes
- JSON parsing robusto con fallback
- Trazabilidad: cada resultado lleva el nombre del agente y tokens usados
"""
from __future__ import annotations
import os
import re
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    agent_name: str
    data: dict
    confianza: float = 0.0
    tokens_input: int = 0
    tokens_output: int = 0
    cached_tokens: int = 0
    error: Optional[str] = None

    def was_cached(self) -> bool:
        return self.cached_tokens > 0

    def cost_usd(self, model: str) -> float:
        """Estimación de costo en USD."""
        if "haiku" in model:
            input_price, output_price, cache_price = 0.80, 4.0, 0.08
        else:
            input_price, output_price, cache_price = 3.0, 15.0, 0.30
        mtok = 1_000_000
        return (
            (self.tokens_input - self.cached_tokens) * input_price / mtok +
            self.cached_tokens * cache_price / mtok +
            self.tokens_output * output_price / mtok
        )


class BaseAgent(ABC):
    """
    Agente base. Subclases definen:
    - model: modelo de Claude a usar
    - system_prompt: instrucciones especializadas (se cachea)
    - max_tokens: límite de respuesta
    - relevant_patterns: regex para extraer secciones relevantes del texto
    """
    model: str = "claude-haiku-4-5-20251001"
    system_prompt: str = ""
    max_tokens: int = 800
    relevant_patterns: list[str] = []

    @property
    def name(self) -> str:
        return self.__class__.__name__

    def route_text(self, text: str, max_chars: int = 4000) -> str:
        """
        Extrae las secciones del texto relevantes para este agente.
        Si no hay patrones, retorna el texto completo truncado.
        """
        if not self.relevant_patterns or not text:
            return text[:max_chars]

        lines = text.split('\n')
        relevant = []
        for line in lines:
            for pat in self.relevant_patterns:
                if re.search(pat, line, re.IGNORECASE):
                    relevant.append(line.strip())
                    break

        routed = '\n'.join(relevant)
        if len(routed) < 200:
            # Muy poco contexto — usar texto completo
            return text[:max_chars]
        return routed[:max_chars]

    async def run(self, text: str, base_data: Any) -> AgentResult:
        """Punto de entrada principal del agente."""
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            return AgentResult(agent_name=self.name, data={}, error="ANTHROPIC_API_KEY no configurada")

        routed_text = self.route_text(text)
        user_content = self._build_user_prompt(routed_text, base_data)

        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=api_key)

            response = await client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=[{
                    "type": "text",
                    "text": self.system_prompt,
                    "cache_control": {"type": "ephemeral"},  # Cachear system prompt
                }],
                messages=[{"role": "user", "content": user_content}],
            )

            raw = response.content[0].text.strip()
            parsed = _parse_json(raw)

            usage = response.usage
            cached = getattr(usage, 'cache_read_input_tokens', 0) or 0

            result = AgentResult(
                agent_name=self.name,
                data=parsed,
                confianza=self._score(parsed),
                tokens_input=usage.input_tokens,
                tokens_output=usage.output_tokens,
                cached_tokens=cached,
            )
            logger.info(
                f"{self.name}: {len(parsed)} campos, conf={result.confianza:.2f}, "
                f"tokens={usage.input_tokens}(+{cached} cached)"
            )
            return result

        except Exception as e:
            logger.error(f"{self.name} error: {e}")
            return AgentResult(agent_name=self.name, data={}, error=str(e))

    @abstractmethod
    def _build_user_prompt(self, text: str, base_data: Any) -> str:
        """Construye el prompt de usuario específico del agente."""

    @abstractmethod
    def _score(self, parsed: dict) -> float:
        """Calcula confianza 0-1 basado en campos extraídos."""


def _parse_json(raw: str) -> dict:
    """Parsea JSON de la respuesta, tolerante a markdown y texto extra."""
    # Eliminar bloques markdown
    if "```" in raw:
        blocks = re.findall(r'```(?:json)?\s*([\s\S]*?)```', raw)
        if blocks:
            raw = blocks[0].strip()

    # Buscar primer objeto JSON en el texto
    match = re.search(r'\{[\s\S]*\}', raw)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    try:
        return json.loads(raw)
    except Exception:
        return {}
