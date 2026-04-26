"""
VISIONARY Python SDK
Typed async client for the VISIONARY multimodal extraction API.

Usage:
    from visionary import VisionaryClient, ExtractionMode, TemplateType

    async with VisionaryClient(api_key="vk_...") as client:
        result = await client.extract_url(
            "https://example.com/invoice.pdf",
            mode=ExtractionMode.TEMPLATE,
            template=TemplateType.INVOICE,
        )
        print(result.data)
"""

from __future__ import annotations

import asyncio
import base64
import mimetypes
import time
from contextlib import asynccontextmanager
from enum import Enum
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Union
from uuid import uuid4

import httpx

__version__ = "1.0.0"
__all__ = [
    "VisionaryClient",
    "ExtractionMode",
    "TemplateType",
    "Provider",
    "ExtractionResult",
    "BatchJob",
    "VisionaryError",
    "AuthenticationError",
    "RateLimitError",
    "ExtractionError",
]


#  Enums (mirrors API) 


class ExtractionMode(str, Enum):
    AUTO = "auto"
    SCHEMA = "schema"
    TEMPLATE = "template"
    TABLE = "table"
    KEY_VALUE = "key_value"
    RAW = "raw"


class TemplateType(str, Enum):
    INVOICE = "invoice"
    RECEIPT = "receipt"
    FORM = "form"
    BUSINESS_CARD = "business_card"
    ID_DOCUMENT = "id_document"
    MEDICAL_REPORT = "medical_report"
    CONTRACT = "contract"
    RESUME = "resume"
    PRODUCT_LABEL = "product_label"
    TABLE_DATA = "table_data"
    CHART_DATA = "chart_data"


class Provider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"
    AUTO = "auto"


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


#  Errors


class VisionaryError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, error_code: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class AuthenticationError(VisionaryError):
    pass


class RateLimitError(VisionaryError):
    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message, status_code=429, error_code="rate_limit_exceeded")
        self.retry_after = retry_after


class ExtractionError(VisionaryError):
    pass


class TimeoutError(VisionaryError):
    pass


#  Result Types


class FieldConfidence:
    def __init__(self, score: float, is_low_confidence: bool, reason: Optional[str] = None):
        self.score = score
        self.is_low_confidence = is_low_confidence
        self.reason = reason

    def __repr__(self) -> str:
        return f"FieldConfidence(score={self.score:.2f}, low={self.is_low_confidence})"


class UsageStats:
    def __init__(self, data: Dict[str, Any]):
        self.input_tokens: int = data.get("input_tokens", 0)
        self.output_tokens: int = data.get("output_tokens", 0)
        self.total_tokens: int = data.get("total_tokens", 0)
        self.provider: str = data.get("provider", "unknown")
        self.model: str = data.get("model", "unknown")
        self.latency_ms: float = data.get("latency_ms", 0.0)

    def __repr__(self) -> str:
        return (
            f"UsageStats(tokens={self.total_tokens}, "
            f"provider={self.provider}, latency={self.latency_ms:.0f}ms)"
        )


class ExtractionResult:
    """Structured result from a single extraction."""

    def __init__(self, raw: Dict[str, Any]):
        result = raw.get("result", {})
        self.id: str = raw.get("id", "")
        self.data: Dict[str, Any] = result.get("data", {})
        self.raw_text: Optional[str] = result.get("raw_text")
        self.schema_valid: Optional[bool] = result.get("schema_valid")
        self.schema_errors: Optional[List[str]] = result.get("schema_errors")
        self.low_confidence_fields: List[str] = result.get("low_confidence_fields", [])
        self.extraction_mode: str = result.get("extraction_mode", "auto")
        self.template_used: Optional[str] = result.get("template_used")
        self.pages_processed: int = result.get("pages_processed", 1)
        self.metadata: Dict[str, Any] = raw.get("metadata", {})
        self.usage: Optional[UsageStats] = UsageStats(raw["usage"]) if "usage" in raw else None

        # Parse confidence
        raw_conf = result.get("confidence") or {}
        self.confidence: Dict[str, FieldConfidence] = {
            field: FieldConfidence(
                score=meta.get("score", 1.0) if isinstance(meta, dict) else float(meta),
                is_low_confidence=meta.get("is_low_confidence", False) if isinstance(meta, dict) else False,
                reason=meta.get("reason") if isinstance(meta, dict) else None,
            )
            for field, meta in raw_conf.items()
        }

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def __repr__(self) -> str:
        keys = list(self.data.keys())[:5]
        return f"ExtractionResult(fields={keys}, mode={self.extraction_mode})"


class BatchJobResult:
    """Result for a single item within a batch."""

    def __init__(self, data: Dict[str, Any]):
        self.id: str = data.get("id", "")
        self.status: str = data.get("status", "unknown")
        self.error: Optional[str] = data.get("error")
        self.metadata: Dict[str, Any] = data.get("metadata", {})

        result_data = data.get("result")
        if result_data:
            # Reconstruct as if it were a top-level extract response
            self.result: Optional[ExtractionResult] = ExtractionResult(
                {"result": result_data, "usage": data.get("usage", {}), "id": self.id}
            )
        else:
            self.result = None

    @property
    def data(self) -> Optional[Dict[str, Any]]:
        return self.result.data if self.result else None

    def __repr__(self) -> str:
        return f"BatchJobResult(id={self.id!r}, status={self.status!r})"


class BatchJob:
    """Async batch job handle."""

    def __init__(self, data: Dict[str, Any], client: "VisionaryClient"):
        self._client = client
        self.id: str = data["id"]
        self.status: str = data["status"]
        self.total: int = data["total"]
        self.completed: int = data.get("completed", 0)
        self.failed: int = data.get("failed", 0)
        self.progress_pct: float = data.get("progress_pct", 0.0)
        self.items: List[BatchJobResult] = []

    async def refresh(self) -> "BatchJob":
        """Fetch latest status from API."""
        data = await self._client._get(f"/jobs/{self.id}/status")
        self.status = data["status"]
        self.completed = data.get("completed", 0)
        self.failed = data.get("failed", 0)
        self.progress_pct = data.get("progress_pct", 0.0)
        return self

    async def results(self) -> List[BatchJobResult]:
        """Fetch full results (only meaningful when completed)."""
        data = await self._client._get(f"/jobs/{self.id}")
        self.items = [BatchJobResult(item) for item in data.get("items", [])]
        return self.items

    async def wait(
        self,
        poll_interval: float = 2.0,
        timeout: float = 600.0,
        on_progress=None,
    ) -> "BatchJob":
        """
        Poll until job completes or timeout is reached.

        Args:
            poll_interval: Seconds between polls.
            timeout: Max seconds to wait.
            on_progress: Optional callback(job) called on each poll.
        """
        start = time.monotonic()
        while True:
            await self.refresh()
            if on_progress:
                on_progress(self)
            if self.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                break
            if time.monotonic() - start > timeout:
                raise TimeoutError(f"Job {self.id} did not complete within {timeout}s")
            await asyncio.sleep(poll_interval)
        return self

    def __repr__(self) -> str:
        return (
            f"BatchJob(id={self.id!r}, status={self.status!r}, "
            f"progress={self.progress_pct}%, {self.completed}/{self.total})"
        )


#  Client 


class VisionaryClient:
    """
    Async Python client for the VISIONARY API.

    Examples:
        # Context manager (recommended)
        async with VisionaryClient(api_key="vk_...") as client:
            result = await client.extract_url("https://example.com/invoice.jpg")

        # Manual lifecycle
        client = VisionaryClient(api_key="vk_...")
        await client.__aenter__()
        result = await client.extract_file("/path/to/receipt.png")
        await client.__aexit__(None, None, None)
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:8000/v1",
        timeout: float = 120.0,
        max_retries: int = 2,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "VisionaryClient":
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "X-API-Key": self.api_key,
                "User-Agent": f"visionary-python/{__version__}",
            },
            timeout=self.timeout,
        )
        return self

    async def __aexit__(self, *args) -> None:
        if self._client:
            await self._client.aclose()

    # Core request helper

    async def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with VisionaryClient(...) as client:'")

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = await self._client.request(method, path, **kwargs)
                if resp.status_code == 401:
                    raise AuthenticationError("Invalid or missing API key.", status_code=401)
                if resp.status_code == 403:
                    raise AuthenticationError("Forbidden. Check your API key.", status_code=403)
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 60))
                    raise RateLimitError(f"Rate limit exceeded. Retry after {retry_after}s.", retry_after=retry_after)
                if resp.status_code == 408:
                    raise TimeoutError("Extraction timed out on the server.", status_code=408)
                if resp.status_code >= 500:
                    detail = resp.json().get("detail", {}) if resp.content else {}
                    msg = detail.get("message", resp.text) if isinstance(detail, dict) else str(detail)
                    raise ExtractionError(f"Server error: {msg}", status_code=resp.status_code)
                resp.raise_for_status()
                return resp.json()
            except (AuthenticationError, RateLimitError, TimeoutError):
                raise  # Never retry auth/rate errors
            except ExtractionError as e:
                if resp.status_code < 500:
                    raise
                last_error = e
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
            except httpx.TimeoutException:
                last_error = TimeoutError("Request timed out.")
                if attempt < self.max_retries:
                    await asyncio.sleep(1)
            except httpx.RequestError as e:
                last_error = VisionaryError(f"Request error: {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(1)

        raise last_error or VisionaryError("Request failed after retries.")

    async def _get(self, path: str, **kwargs) -> Dict[str, Any]:
        return await self._request("GET", path, **kwargs)

    async def _post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", path, json=body)

    # Input builders 

    @staticmethod
    def _url_input(url: str, label: Optional[str] = None) -> Dict[str, Any]:
        input_type = "pdf_url" if url.lower().endswith(".pdf") else "image_url"
        inp: Dict[str, Any] = {"type": input_type, "data": url}
        if label:
            inp["label"] = label
        return inp

    @staticmethod
    def _file_input(path: Union[str, Path], label: Optional[str] = None) -> Dict[str, Any]:
        p = Path(path)
        media_type, _ = mimetypes.guess_type(str(p))
        if not media_type:
            suffix = p.suffix.lower()
            media_type = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".webp": "image/webp",
                ".gif": "image/gif", ".tiff": "image/tiff",
                ".pdf": "application/pdf",
            }.get(suffix, "image/jpeg")

        with open(p, "rb") as f:
            data = base64.b64encode(f.read()).decode()

        input_type = "pdf_base64" if media_type == "application/pdf" else "image_base64"
        inp: Dict[str, Any] = {"type": input_type, "data": data, "media_type": media_type}
        if label:
            inp["label"] = label
        return inp

    @staticmethod
    def _b64_input(data: str, media_type: str = "image/jpeg", label: Optional[str] = None) -> Dict[str, Any]:
        input_type = "pdf_base64" if "pdf" in media_type else "image_base64"
        inp: Dict[str, Any] = {"type": input_type, "data": data, "media_type": media_type}
        if label:
            inp["label"] = label
        return inp

    def _build_extraction_config(
        self,
        mode: ExtractionMode,
        schema: Optional[Dict[str, Any]],
        template: Optional[TemplateType],
        instructions: Optional[str],
        confidence_threshold: float,
        include_confidence: bool,
        language: str,
        strict_schema: bool,
    ) -> Dict[str, Any]:
        cfg: Dict[str, Any] = {
            "mode": mode.value,
            "confidence_threshold": confidence_threshold,
            "include_confidence": include_confidence,
            "language": language,
            "strict_schema": strict_schema,
        }
        if schema:
            cfg["json_schema"] = schema
        if template:
            cfg["template"] = template.value
        if instructions:
            cfg["instructions"] = instructions
        return cfg

    def _build_model_config(
        self,
        provider: Provider,
        model: Optional[str],
        temperature: float,
        max_tokens: int,
        timeout_seconds: int,
        fallback_providers: List[Provider],
    ) -> Dict[str, Any]:
        return {
            "provider": provider.value,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout_seconds": timeout_seconds,
            "fallback_providers": [p.value for p in fallback_providers],
        }

    # High-level extraction methods

    async def extract_url(
        self,
        url: str,
        *,
        mode: ExtractionMode = ExtractionMode.AUTO,
        schema: Optional[Dict[str, Any]] = None,
        template: Optional[TemplateType] = None,
        instructions: Optional[str] = None,
        confidence_threshold: float = 0.0,
        include_confidence: bool = True,
        language: str = "auto",
        strict_schema: bool = False,
        provider: Provider = Provider.AUTO,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        timeout_seconds: int = 60,
        fallback_providers: Optional[List[Provider]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        """Extract structured data from an image/PDF URL."""
        body = {
            "inputs": [self._url_input(url)],
            "extraction": self._build_extraction_config(
                mode, schema, template, instructions,
                confidence_threshold, include_confidence, language, strict_schema,
            ),
            "model": self._build_model_config(
                provider, model, temperature, max_tokens, timeout_seconds,
                fallback_providers or [],
            ),
            "metadata": metadata or {},
        }
        raw = await self._post("/extract", body)
        return ExtractionResult(raw)

    async def extract_file(
        self,
        path: Union[str, Path],
        *,
        mode: ExtractionMode = ExtractionMode.AUTO,
        schema: Optional[Dict[str, Any]] = None,
        template: Optional[TemplateType] = None,
        instructions: Optional[str] = None,
        confidence_threshold: float = 0.0,
        include_confidence: bool = True,
        language: str = "auto",
        strict_schema: bool = False,
        provider: Provider = Provider.AUTO,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        timeout_seconds: int = 60,
        fallback_providers: Optional[List[Provider]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        """Extract structured data from a local file."""
        body = {
            "inputs": [self._file_input(path)],
            "extraction": self._build_extraction_config(
                mode, schema, template, instructions,
                confidence_threshold, include_confidence, language, strict_schema,
            ),
            "model": self._build_model_config(
                provider, model, temperature, max_tokens, timeout_seconds,
                fallback_providers or [],
            ),
            "metadata": metadata or {},
        }
        raw = await self._post("/extract", body)
        return ExtractionResult(raw)

    async def extract_base64(
        self,
        data: str,
        media_type: str = "image/jpeg",
        *,
        mode: ExtractionMode = ExtractionMode.AUTO,
        schema: Optional[Dict[str, Any]] = None,
        template: Optional[TemplateType] = None,
        instructions: Optional[str] = None,
        confidence_threshold: float = 0.0,
        include_confidence: bool = True,
        language: str = "auto",
        strict_schema: bool = False,
        provider: Provider = Provider.AUTO,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        timeout_seconds: int = 60,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        """Extract structured data from base64-encoded image/PDF."""
        body = {
            "inputs": [self._b64_input(data, media_type)],
            "extraction": self._build_extraction_config(
                mode, schema, template, instructions,
                confidence_threshold, include_confidence, language, strict_schema,
            ),
            "model": self._build_model_config(provider, model, temperature, max_tokens, timeout_seconds, []),
            "metadata": metadata or {},
        }
        raw = await self._post("/extract", body)
        return ExtractionResult(raw)

    async def extract_multi(
        self,
        inputs: List[Dict[str, Any]],
        *,
        mode: ExtractionMode = ExtractionMode.AUTO,
        schema: Optional[Dict[str, Any]] = None,
        template: Optional[TemplateType] = None,
        instructions: Optional[str] = None,
        confidence_threshold: float = 0.0,
        include_confidence: bool = True,
        language: str = "auto",
        provider: Provider = Provider.AUTO,
        model: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        """
        Extract from multiple inputs together (e.g., multi-page PDF as images).
        Each input is a dict: {"url": "..."} or {"file": "/path"} or {"base64": "...", "media_type": "..."}.
        """
        resolved = []
        for inp in inputs:
            if "url" in inp:
                resolved.append(self._url_input(inp["url"], inp.get("label")))
            elif "file" in inp:
                resolved.append(self._file_input(inp["file"], inp.get("label")))
            elif "base64" in inp:
                resolved.append(self._b64_input(inp["base64"], inp.get("media_type", "image/jpeg"), inp.get("label")))
            else:
                raise ValueError(f"Invalid input dict: {inp}. Use 'url', 'file', or 'base64' key.")

        body = {
            "inputs": resolved,
            "extraction": self._build_extraction_config(
                mode, schema, template, instructions,
                confidence_threshold, include_confidence, language, False,
            ),
            "model": self._build_model_config(provider, model, 0.1, 4096, 60, []),
            "metadata": metadata or {},
        }
        raw = await self._post("/extract", body)
        return ExtractionResult(raw)

    #  Batch methods 

    async def batch_extract(
        self,
        items: List[Dict[str, Any]],
        *,
        mode: ExtractionMode = ExtractionMode.AUTO,
        schema: Optional[Dict[str, Any]] = None,
        template: Optional[TemplateType] = None,
        instructions: Optional[str] = None,
        provider: Provider = Provider.AUTO,
        concurrency: int = 5,
        webhook_url: Optional[str] = None,
        webhook_secret: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BatchJob:
        """
        Submit a batch of extractions.

        Each item: {"url": "..."} | {"file": "/path"} | {"base64": "...", "media_type": "..."}.
        Optionally add "id" and "metadata" keys per item.

        Returns a BatchJob handle. Call .wait() to poll until completion.
        """
        batch_items = []
        for item in items:
            item_id = item.pop("id", str(uuid4()))
            item_metadata = item.pop("metadata", {})
            if "url" in item:
                inp = self._url_input(item["url"], item.get("label"))
            elif "file" in item:
                inp = self._file_input(item["file"], item.get("label"))
            elif "base64" in item:
                inp = self._b64_input(item["base64"], item.get("media_type", "image/jpeg"))
            else:
                raise ValueError(f"Invalid batch item: {item}")

            batch_items.append({"id": item_id, "inputs": [inp], "metadata": item_metadata})

        body: Dict[str, Any] = {
            "items": batch_items,
            "extraction": self._build_extraction_config(
                mode, schema, template, instructions, 0.0, True, "auto", False,
            ),
            "model": self._build_model_config(provider, None, 0.1, 4096, 60, []),
            "concurrency": concurrency,
            "metadata": metadata or {},
        }
        if webhook_url:
            body["webhook"] = {"url": webhook_url, "secret": webhook_secret or ""}

        raw = await self._post("/batch", body)
        return BatchJob(raw, self)

    # Job management 

    async def get_job(self, job_id: str) -> BatchJob:
        raw = await self._get(f"/jobs/{job_id}")
        job = BatchJob(raw, self)
        job.items = [BatchJobResult(item) for item in raw.get("items", [])]
        return job

    async def list_jobs(self, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        return await self._get(f"/jobs?limit={limit}&offset={offset}")

    async def delete_job(self, job_id: str) -> bool:
        result = await self._request("DELETE", f"/jobs/{job_id}")
        return result.get("deleted", False)

    #  Templates & Providers 

    async def list_templates(self) -> List[Dict[str, Any]]:
        return await self._get("/templates")

    async def get_template(self, template: TemplateType) -> Dict[str, Any]:
        return await self._get(f"/templates/{template.value}")

    async def list_providers(self) -> Dict[str, Any]:
        return await self._get("/providers")

    async def health(self) -> Dict[str, Any]:
        return await self._request("GET", "/health")
