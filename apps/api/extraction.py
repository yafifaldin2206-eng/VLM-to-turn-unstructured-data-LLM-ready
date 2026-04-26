"""
Core extraction engine.
Orchestrates providers, parses output, validates schemas, computes confidence.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

import jsonschema

from app.core.logging import get_logger
from app.models.schemas import (
    BoundingBox,
    ExtractionConfig,
    ExtractionMode,
    ExtractionResult,
    FieldConfidence,
    ImageInput,
    ModelConfig,
    UsageStats,
)
from app.services.providers import PromptBuilder, run_with_fallback

logger = get_logger(__name__)


class ExtractionEngine:
    """
    Core engine: build prompts → call providers → parse → validate → return.
    """

    async def run(
        self,
        inputs: List[ImageInput],
        extraction: ExtractionConfig,
        model_config: ModelConfig,
    ) -> Tuple[ExtractionResult, UsageStats]:
        """Run the full extraction pipeline."""
        system_prompt = PromptBuilder.build_system_prompt(extraction)
        user_prompt = PromptBuilder.build_user_prompt(extraction, len(inputs))

        raw_text, usage = await run_with_fallback(
            inputs=inputs,
            extraction=extraction,
            model_config=model_config,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        logger.info(
            "Raw extraction completed",
            tokens=usage.total_tokens,
            latency_ms=round(usage.latency_ms, 1),
            provider=usage.provider,
        )

        result = self._parse_and_structure(raw_text, extraction)
        return result, usage

    def _parse_and_structure(
        self,
        raw_text: str,
        extraction: ExtractionConfig,
    ) -> ExtractionResult:
        """Parse raw model output into a structured ExtractionResult."""
        # Clean the raw text
        cleaned = self._clean_json_output(raw_text)

        try:
            parsed: Dict[str, Any] = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning("JSON parse failed, attempting recovery", error=str(e))
            parsed = self._recover_json(raw_text)

        # Separate confidence scores from data
        data, confidence_map = self._extract_confidence(parsed, extraction)

        # Schema validation
        schema_valid = None
        schema_errors = None
        if extraction.mode == ExtractionMode.SCHEMA and extraction.schema:
            schema_valid, schema_errors = self._validate_schema(data, extraction.schema)
            if not schema_valid and extraction.strict_schema:
                raise ValueError(f"Schema validation failed: {'; '.join(schema_errors or [])}")

        # Identify low-confidence fields
        low_conf_fields = []
        if confidence_map and extraction.confidence_threshold > 0:
            for field, conf in confidence_map.items():
                if conf.score < extraction.confidence_threshold:
                    conf.is_low_confidence = True
                    low_conf_fields.append(field)

        return ExtractionResult(
            data=data,
            raw_text=raw_text if extraction.mode == ExtractionMode.RAW else None,
            confidence=confidence_map if extraction.include_confidence and confidence_map else None,
            schema_valid=schema_valid,
            schema_errors=schema_errors,
            low_confidence_fields=low_conf_fields,
            extraction_mode=extraction.mode,
            template_used=extraction.template,
            pages_processed=1,
        )

    def _clean_json_output(self, text: str) -> str:
        """Strip markdown fences, BOM, leading/trailing noise."""
        text = text.strip()
        text = text.lstrip("\ufeff")
        # Remove ```json ... ``` fences
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
        text = text.strip()
        return text

    def _recover_json(self, raw: str) -> Dict[str, Any]:
        """Attempt heuristic JSON recovery from malformed output."""
        # Try to find the outermost JSON object
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = raw[start:end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        # Last resort: return raw as text field
        logger.error("JSON recovery failed, wrapping in raw_text field")
        return {"_raw_output": raw, "_parse_error": "Failed to parse structured output"}

    def _extract_confidence(
        self,
        parsed: Dict[str, Any],
        extraction: ExtractionConfig,
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, FieldConfidence]]]:
        """
        Separate _confidence metadata from actual data fields.
        The model is instructed to embed a _confidence key alongside data.
        """
        if not extraction.include_confidence:
            return parsed, None

        raw_confidence = parsed.pop("_confidence", None)
        confidence_map: Dict[str, FieldConfidence] = {}

        if isinstance(raw_confidence, dict):
            for field, meta in raw_confidence.items():
                if isinstance(meta, dict):
                    score = float(meta.get("score", 1.0))
                    confidence_map[field] = FieldConfidence(
                        score=min(max(score, 0.0), 1.0),
                        is_low_confidence=score < extraction.confidence_threshold,
                        reason=meta.get("reason"),
                    )
                elif isinstance(meta, (int, float)):
                    score = float(meta)
                    confidence_map[field] = FieldConfidence(
                        score=min(max(score, 0.0), 1.0),
                        is_low_confidence=score < extraction.confidence_threshold,
                    )

        # If no confidence was returned, assign defaults based on extraction mode
        if not confidence_map:
            return parsed, None

        return parsed, confidence_map

    def _validate_schema(
        self,
        data: Dict[str, Any],
        schema: Dict[str, Any],
    ) -> Tuple[bool, Optional[List[str]]]:
        """Validate extracted data against a JSON Schema."""
        try:
            validator = jsonschema.Draft7Validator(schema)
            errors = list(validator.iter_errors(data))
            if errors:
                error_msgs = [f"{'.'.join(str(p) for p in e.path) or 'root'}: {e.message}" for e in errors[:10]]
                return False, error_msgs
            return True, None
        except (jsonschema.SchemaError, jsonschema.exceptions.UnknownType, Exception) as e:
            return False, [f"Invalid schema: {getattr(e, 'message', str(e))}"]


# Singleton
engine = ExtractionEngine()
