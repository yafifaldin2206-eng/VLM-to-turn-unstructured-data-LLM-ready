"""
Pydantic models for VISIONARY API.
All request/response schemas with full validation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


# Enums


class Provider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"
    AUTO = "auto"  # Router picks best available


class InputType(str, Enum):
    IMAGE_URL = "image_url"
    IMAGE_BASE64 = "image_base64"
    PDF_URL = "pdf_url"
    PDF_BASE64 = "pdf_base64"
    WEB_URL = "web_url"  # Screenshot + extract


class ExtractionMode(str, Enum):
    SCHEMA = "schema"          # User provides JSON Schema → validated output
    AUTO = "auto"              # Model infers best structure
    TEMPLATE = "template"      # Use built-in template
    RAW = "raw"                # Raw markdown/text extraction (no structuring)
    TABLE = "table"            # Force tabular extraction
    KEY_VALUE = "key_value"    # Force flat KV extraction


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


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ImageFormat(str, Enum):
    JPEG = "image/jpeg"
    PNG = "image/png"
    WEBP = "image/webp"
    GIF = "image/gif"
    TIFF = "image/tiff"
    PDF = "application/pdf"


# ─── Input Models 


class ImageInput(BaseModel):
    """A single image or PDF input."""

    type: InputType
    data: str = Field(description="URL or base64-encoded data")
    media_type: Optional[ImageFormat] = Field(
        default=None,
        description="Required for base64 inputs. Auto-detected for URLs.",
    )
    page_range: Optional[str] = Field(
        default=None,
        description="For PDFs: '1', '1-3', '2,4,6', 'all'. Default: 'all'.",
        examples=["1-5", "all", "1,3,5"],
    )
    label: Optional[str] = Field(
        default=None,
        description="Optional label for this input, useful in batch/multi-input requests.",
    )

    @field_validator("data")
    @classmethod
    def validate_data(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError("data cannot be empty")
        return v.strip()


class ExtractionConfig(BaseModel):
    """Controls how extraction is performed."""

    mode: ExtractionMode = ExtractionMode.AUTO
    schema: Optional[Dict[str, Any]] = Field(
        default=None,
        description="JSON Schema for structured output. Required when mode=schema.",
        alias="json_schema",
    )
    template: Optional[TemplateType] = Field(
        default=None,
        description="Built-in template. Required when mode=template.",
    )
    instructions: Optional[str] = Field(
        default=None,
        max_length=4000,
        description="Additional natural language instructions for the extraction.",
    )
    confidence_threshold: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Fields below this confidence will be flagged as low_confidence.",
    )
    include_confidence: bool = Field(
        default=True,
        description="Include per-field confidence scores in output.",
    )
    include_bounding_boxes: bool = Field(
        default=False,
        description="Include normalized bounding box coordinates for each extracted field.",
    )
    language: str = Field(
        default="auto",
        description="Target language for extraction (ISO 639-1 or 'auto').",
    )
    strict_schema: bool = Field(
        default=False,
        description="If true, reject output that doesn't fully conform to the provided schema.",
    )

    @model_validator(mode="after")
    def validate_mode_requirements(self) -> ExtractionConfig:
        if self.mode == ExtractionMode.SCHEMA and not self.schema:
            raise ValueError("json_schema is required when mode='schema'")
        if self.mode == ExtractionMode.TEMPLATE and not self.template:
            raise ValueError("template is required when mode='template'")
        return self

    model_config = {"populate_by_name": True}


class ModelConfig(BaseModel):
    """Provider and model selection."""

    provider: Provider = Provider.AUTO
    model: Optional[str] = Field(
        default=None,
        description="Specific model override. If None, uses provider default.",
    )
    fallback_providers: List[Provider] = Field(
        default=[],
        description="Ordered list of fallback providers if primary fails.",
        max_length=3,
    )
    temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    max_tokens: int = Field(default=4096, ge=128, le=16384)
    timeout_seconds: int = Field(default=60, ge=5, le=300)


class WebhookConfig(BaseModel):
    """Webhook callback configuration."""

    url: str = Field(description="HTTPS URL to POST results to.")
    secret: Optional[str] = Field(
        default=None,
        description="Optional HMAC-SHA256 signing secret for payload verification.",
    )
    headers: Dict[str, str] = Field(
        default={},
        description="Additional headers to include in webhook requests.",
    )
    include_raw: bool = Field(
        default=False,
        description="Include raw model output in webhook payload.",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("Webhook URL must start with http:// or https://")
        return v


#  Request Models


class ExtractRequest(BaseModel):
    """Single synchronous extraction request."""

    inputs: List[ImageInput] = Field(
        min_length=1,
        max_length=10,
        description="One or more images/PDFs to process together.",
    )
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    metadata: Dict[str, Any] = Field(
        default={},
        description="Arbitrary metadata passed through to the response.",
    )


class BatchItem(BaseModel):
    """Single item in a batch request."""

    id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Client-assigned ID for this item.",
    )
    inputs: List[ImageInput] = Field(min_length=1, max_length=10)
    extraction: Optional[ExtractionConfig] = None  # Falls back to batch-level config
    metadata: Dict[str, Any] = {}


class BatchRequest(BaseModel):
    """Async batch processing request."""

    items: List[BatchItem] = Field(
        min_length=1,
        description="List of extraction items.",
    )
    extraction: ExtractionConfig = Field(
        default_factory=ExtractionConfig,
        description="Default extraction config applied to items without their own.",
    )
    model: ModelConfig = Field(default_factory=ModelConfig)
    webhook: Optional[WebhookConfig] = None
    concurrency: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Max concurrent extractions within the batch.",
    )
    metadata: Dict[str, Any] = {}

    @field_validator("items")
    @classmethod
    def validate_batch_size(cls, v: list) -> list:
        from app.core.config import settings
        if len(v) > settings.MAX_BATCH_SIZE:
            raise ValueError(f"Batch size exceeds maximum of {settings.MAX_BATCH_SIZE}")
        return v


class ReExtractRequest(BaseModel):
    """Re-run extraction on a completed job with new config."""

    job_id: str
    extraction: ExtractionConfig
    model: Optional[ModelConfig] = None


# Output Models


class FieldConfidence(BaseModel):
    """Confidence metadata for a single extracted field."""

    score: float = Field(ge=0.0, le=1.0)
    is_low_confidence: bool
    reason: Optional[str] = None


class BoundingBox(BaseModel):
    """Normalized bounding box [0, 1]."""

    x: float
    y: float
    width: float
    height: float
    page: int = 1


class ExtractionResult(BaseModel):
    """Result of a single extraction."""

    data: Dict[str, Any] = Field(description="The extracted structured data.")
    raw_text: Optional[str] = Field(
        default=None,
        description="Raw text/markdown from the model before structuring.",
    )
    confidence: Optional[Dict[str, FieldConfidence]] = Field(
        default=None,
        description="Per-field confidence scores.",
    )
    bounding_boxes: Optional[Dict[str, BoundingBox]] = Field(
        default=None,
        description="Per-field bounding boxes.",
    )
    schema_valid: Optional[bool] = Field(
        default=None,
        description="Whether output validated against the provided schema.",
    )
    schema_errors: Optional[List[str]] = None
    low_confidence_fields: List[str] = Field(
        default=[],
        description="Fields flagged as below the confidence threshold.",
    )
    extraction_mode: ExtractionMode
    template_used: Optional[TemplateType] = None
    pages_processed: int = 1


class UsageStats(BaseModel):
    """Token/compute usage."""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    provider: str
    model: str
    latency_ms: float


class ExtractResponse(BaseModel):
    """Response for synchronous extraction."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    status: str = "completed"
    result: ExtractionResult
    usage: UsageStats
    metadata: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Job Models


class JobResult(BaseModel):
    """Result for a single batch item."""

    id: str
    status: JobStatus
    result: Optional[ExtractionResult] = None
    usage: Optional[UsageStats] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    metadata: Dict[str, Any] = {}
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class Job(BaseModel):
    """Async batch job."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    status: JobStatus = JobStatus.QUEUED
    items: List[JobResult] = []
    total: int = 0
    completed: int = 0
    failed: int = 0
    webhook: Optional[WebhookConfig] = None
    metadata: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    @property
    def progress_pct(self) -> float:
        if self.total == 0:
            return 0.0
        return round((self.completed + self.failed) / self.total * 100, 1)


class JobStatusResponse(BaseModel):
    """Lightweight job status (no results)."""

    id: str
    status: JobStatus
    total: int
    completed: int
    failed: int
    progress_pct: float
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error: Optional[str] = None


class JobDetailResponse(Job):
    """Full job with all results."""
    pass


#  Template Models


class TemplateInfo(BaseModel):
    id: TemplateType
    name: str
    description: str
    output_schema: Dict[str, Any]
    example_fields: List[str]
