from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = ROOT / "model" / "training" / "datasets"
DEFAULT_MODEL_DIR = PACKAGE_ROOT / "models" / "Qwen3.5-4B"
DEFAULT_ADAPTER_DIR = PACKAGE_ROOT / "models" / "best_adapter"
DEFAULT_TASK = "oct_aux_4class"
TASK_LABELS = {
    "oct_uveitis_4class": [
        "Intermediate+Posterior Uveitis",
        "Normal",
        "Panuveitis",
        "RRD-PVR",
    ],
    "fundus_toxo_binary": ["healthy", "toxoplasmosis"],
    "eye_five_class": [
        "Cataract",
        "Conjunctivitis",
        "Eyelid",
        "Normal",
        "Uveitis",
    ],
    "oct_aux_4class": ["CNV", "DME", "DRUSEN", "NORMAL"],
    "uwf_7class": ["AMD", "DR", "Healthy", "PM", "RD", "RVO", "Uveitis"],
    "uwf_uveitis_binary": ["non_uveitis", "uveitis"],
}
DEFAULT_IMAGE_PIXELS = 65_536
DEFAULT_MAX_NEW_TOKENS = 128
DEFAULT_THINKING_MAX_NEW_TOKENS = 512
DEFAULT_MAX_IMAGES = 4
DEFAULT_MAX_IMAGE_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_IMAGE_PIXELS = 40_000_000
MAX_ALLOWED_IMAGES = 8
MAX_ALLOWED_IMAGE_BYTES = 50 * 1024 * 1024
MAX_ALLOWED_DECODED_PIXELS = 100_000_000
MAX_FINDINGS = 32
LOG = logging.getLogger("uveitis.model_runtime")
logging.basicConfig(level=logging.INFO)


class CaseImageRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=128)
    kind: str | None = Field(default=None, max_length=64)
    local_path: str | None = Field(default=None, max_length=4096)


class CaseRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    case_id: str = Field(min_length=1, max_length=128)
    patient_age: int | None = Field(default=None, ge=0, le=150)
    patient_sex: str | None = Field(default=None, max_length=32)
    complaint: str = Field(default="", max_length=4000)
    medical_history: str = Field(default="", max_length=8000)
    affected_eye: str | None = Field(default=None, max_length=32)
    images: list[CaseImageRequest] = Field(
        default_factory=list,
        max_length=MAX_ALLOWED_IMAGES,
    )


class JudgeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    task: str = DEFAULT_TASK
    case: CaseRequest
    output_schema: dict[str, Any] | None = None
    constraints: list[str] = Field(default_factory=list, max_length=32)
    tools: list[str] = Field(default_factory=list, max_length=8)
    tool_results: list[dict[str, Any]] = Field(default_factory=list, max_length=8)
    enable_thinking: bool | None = Field(
        default=None,
        description="Per-request override; None uses the service default.",
    )


class JudgeToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class JudgeResult(BaseModel):
    label: str
    confidence: float
    impression: str
    findings: list[dict[str, Any]]
    recommendations: list[str] = Field(default_factory=list)
    requires_human_review: Literal[True] = True


class JudgeResponse(BaseModel):
    status: Literal["result", "tool_call"] = "result"
    result: JudgeResult | None = None
    tool_call: JudgeToolCall | None = None
    task: str
    model: str
    adapter_sha256: str
    latency_ms: int
    generated_at: str
    truncated: bool
    thinking: str = ""
    thinking_mode: bool
    thinking_fallback_used: bool = False
    peak_allocated_gib: float | None = None
    peak_reserved_gib: float | None = None
    research_use_only: Literal[True] = True


app = FastAPI(
    title="Uveitis Model Runtime",
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)


def _path_status(path: Path) -> str:
    return "ready" if path.is_dir() else "missing"


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


def _paths() -> tuple[Path, Path]:
    model_dir = Path(
        os.environ.get("MODEL_RUNTIME_MODEL_DIR", DEFAULT_MODEL_DIR)
    ).resolve()
    adapter_dir = Path(
        os.environ.get("MODEL_RUNTIME_ADAPTER_DIR", DEFAULT_ADAPTER_DIR)
    ).resolve()
    return model_dir, adapter_dir


def _thinking_enabled() -> bool:
    return os.environ.get("MODEL_RUNTIME_ENABLE_THINKING", "false").strip().lower() not in {
        "0",
        "false",
        "no",
    }


def _adapter_ready(adapter_dir: Path) -> bool:
    return (
        (adapter_dir / "adapter_config.json").is_file()
        and (adapter_dir / "adapter_model.safetensors").is_file()
    )


def _allowed_image_roots() -> list[Path]:
    configured = os.environ.get("MODEL_RUNTIME_IMAGE_ROOT", "").strip()
    roots = [DATASET_ROOT]
    if configured:
        roots.append(Path(configured))
    return [root.resolve() for root in roots]


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_case_image(image: CaseImageRequest) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", image.id):
        raise HTTPException(status_code=422, detail="Invalid image id")
    roots = _allowed_image_roots()
    configured = os.environ.get("MODEL_RUNTIME_UPLOAD_ROOT", "").strip()
    if configured:
        roots.append(Path(configured).resolve())
    if image.local_path:
        candidate = Path(image.local_path).resolve()
        allowed = any(_is_within(candidate, root) for root in roots)
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail="Image path is outside the configured runtime roots",
            )
    else:
        candidates = [
            candidate
            for root in roots
            for candidate in root.glob(f"**/{image.id}.*")
            if candidate.is_file()
        ]
        if not candidates:
            raise HTTPException(
                status_code=422,
                detail=f"Image not found: {image.id}",
            )
        if len(candidates) > 1:
            raise HTTPException(
                status_code=409,
                detail=f"Image id is ambiguous: {image.id}",
            )
        candidate = candidates[0].resolve()

    if not any(_is_within(candidate, root) for root in roots):
        raise HTTPException(
            status_code=403,
            detail="Image path is outside the configured runtime roots",
        )
    if not candidate.is_file():
        raise HTTPException(status_code=422, detail=f"Image not found: {candidate}")
    if candidate.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(status_code=415, detail="Unsupported image format")
    if candidate.stat().st_size > _env_int(
        "MODEL_RUNTIME_MAX_IMAGE_BYTES",
        DEFAULT_MAX_IMAGE_BYTES,
        1024,
        MAX_ALLOWED_IMAGE_BYTES,
    ):
        raise HTTPException(status_code=413, detail="Image file is too large")
    return candidate


def _task_prompt(task: str) -> str:
    labels = TASK_LABELS[task]
    return (
        "Classify this retinal image. Do not infer any finding that is not "
        "visible. "
        f"Task: {task}. Allowed labels: {json.dumps(labels)}. "
        "Choose exactly one allowed label and return only compact JSON with "
        '{"label":"...","requires_human_review":true}. '
        "Do not state a definitive diagnosis."
    )


def _tool_prompt(tools: list[str], tool_results: list[dict[str, Any]]) -> str:
    prompt = ""
    if "web_search" in tools:
        prompt += (
            " You may request one web literature search when the image alone"
            " is insufficient. To request it, reply only with compact JSON"
            ' {"tool_call":{"name":"web_search","query":"<short query>"}}.'
            " If the visible evidence is already sufficient, skip the search"
            " and return the final compact JSON with"
            ' {"label":"...","confidence":0.0,"impression":"...",'
            '"requires_human_review":true}.'
        )
    for item in tool_results:
        query = str(item.get("query") or "")
        entries = item.get("results") if isinstance(item.get("results"), list) else []
        prompt += f" Web search results for {query!r}:"
        for index, entry in enumerate(entries[:5], start=1):
            if not isinstance(entry, dict):
                continue
            prompt += (
                f" [{index}] {entry.get('title', '')}:"
                f" {str(entry.get('snippet', ''))[:400]}."
            )
        if not entries:
            prompt += " no results."
    return prompt


def _strip_thinking(raw: str) -> tuple[str, str]:
    """Split a Qwen thinking response into answer text and thinking notes."""

    match = re.search(r"<think>(.*?)</think>", raw, flags=re.DOTALL)
    if match:
        thinking = match.group(1).strip()
        answer = (raw[: match.start()] + raw[match.end() :]).strip()
        return answer, thinking
    if raw.lstrip().startswith("<think>"):
        # Generation stopped inside the thinking block; no answer available.
        return "", raw.strip()
    return raw.strip(), ""


def _parse_output(raw: str, task: str, tools: list[str]) -> dict[str, Any]:
    objects = _json_objects(raw)
    if "web_search" in tools:
        tool_payload = next(
            (
                item
                for item in objects
                if isinstance(item.get("tool_call"), dict)
            ),
            None,
        )
        if tool_payload is not None:
            call = dict(tool_payload["tool_call"])
            name = str(call.get("name") or "").strip()
            if name != "web_search":
                raise ValueError(f"Unsupported tool: {name}")
            query = str(call.get("query") or call.get("arguments", {}).get("query") or "").strip()
            if not query:
                raise ValueError("Tool call is missing a query")
            return {
                "status": "tool_call",
                "tool_call": {"name": name, "arguments": {"query": query[:400]}},
            }
    payload = next(
        (
            item
            for item in objects
            if isinstance(item.get("label"), str)
            and item["label"] in TASK_LABELS[task]
        ),
        None,
    )
    if payload is None:
        raise ValueError("Model did not return an allowed structured label")
    return {"status": "result", "result": _parse_result(raw, task)}


def _json_objects(text: str) -> list[dict[str, Any]]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    candidates = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])
    objects: list[dict[str, Any]] = []
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            objects.append(payload)
    return objects


def _confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _short_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _load_rgb_image(path: Path, max_decoded_pixels: int):
    from PIL import Image

    with Image.open(path) as source:
        width, height = source.size
        if width * height > max_decoded_pixels:
            raise ValueError(f"Decoded image is too large: {path.name}")
        return source.convert("RGB")


def _parse_result(raw: str, task: str) -> dict[str, Any]:
    allowed = TASK_LABELS[task]
    objects = _json_objects(raw)
    payload = next(
        (
            item
            for item in objects
            if isinstance(item.get("label"), str)
            and item["label"] in allowed
        ),
        None,
    )
    if payload is None:
        raise ValueError("Model did not return an allowed structured label")

    label = str(payload["label"])
    findings: list[dict[str, Any]] = []
    raw_findings = payload.get("findings")
    for item in raw_findings if isinstance(raw_findings, list) else []:
        if not isinstance(item, dict):
            continue
        finding_label = _short_text(
            item.get("label") or item.get("finding") or item.get("name"),
            256,
        )
        if not finding_label:
            continue
        findings.append(
            {
                "label": finding_label,
                "location": _short_text(item.get("location"), 256),
                "confidence": _confidence(item.get("confidence")),
            }
        )
        if len(findings) >= MAX_FINDINGS:
            break
    if not findings:
        findings = [
            {
                "label": label,
                "location": "",
                "confidence": _confidence(payload.get("confidence")),
            }
        ]

    recommendations = []
    raw_recommendations = payload.get("recommendations")
    for item in (
        raw_recommendations if isinstance(raw_recommendations, list) else []
    ):
        recommendation = _short_text(item, 500)
        if recommendation and recommendation not in recommendations:
            recommendations.append(recommendation)
        if len(recommendations) >= 16:
            break

    return {
        "label": label,
        "confidence": _confidence(payload.get("confidence")),
        "impression": _short_text(payload.get("impression"), 2000),
        "findings": findings,
        "recommendations": recommendations,
        "requires_human_review": True,
    }


class QwenRuntime:
    def __init__(
        self,
        model_dir: Path,
        adapter_dir: Path,
        *,
        image_pixels: int,
        max_new_tokens: int,
        enable_thinking: bool = True,
        thinking_max_new_tokens: int = DEFAULT_THINKING_MAX_NEW_TOKENS,
        inference_wait_seconds: int,
    ) -> None:
        self.model_dir = model_dir
        self.adapter_dir = adapter_dir
        self.image_pixels = image_pixels
        self.max_new_tokens = max_new_tokens
        self.enable_thinking = enable_thinking
        self.thinking_max_new_tokens = thinking_max_new_tokens
        self.inference_wait_seconds = inference_wait_seconds
        self._load_lock = threading.Lock()
        self._inference_lock = threading.Lock()
        self._processor = None
        self._model = None
        self._torch = None
        self._adapter_sha256 = ""

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _load(self) -> None:
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            if not self.model_dir.is_dir() or not _adapter_ready(self.adapter_dir):
                raise RuntimeError("Model base or adapter files are missing")
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            import torch
            from peft import PeftModel
            from transformers import (
                AutoModelForImageTextToText,
                AutoProcessor,
                BitsAndBytesConfig,
            )

            if not torch.cuda.is_available():
                raise RuntimeError("CUDA is not available")
            processor = AutoProcessor.from_pretrained(
                self.model_dir,
                local_files_only=True,
            )
            quantization = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
            )
            base_model = AutoModelForImageTextToText.from_pretrained(
                self.model_dir,
                local_files_only=True,
                quantization_config=quantization,
                torch_dtype=torch.bfloat16,
                device_map={"": 0},
                attn_implementation="sdpa",
                low_cpu_mem_usage=True,
            )
            model = PeftModel.from_pretrained(
                base_model,
                str(self.adapter_dir),
                is_trainable=False,
            )
            model.eval()
            self._adapter_sha256 = _sha256(
                self.adapter_dir / "adapter_model.safetensors"
            )
            self._processor = processor
            self._model = model
            self._torch = torch
            LOG.info(
                "runtime_loaded",
                extra={
                    "allocated_gib": torch.cuda.memory_allocated() / 1024**3,
                    "reserved_gib": torch.cuda.memory_reserved() / 1024**3,
                },
            )

    def load(self) -> None:
        self._load()

    def judge(
        self,
        task: str,
        image_paths: list[Path],
        tools: list[str] | None = None,
        tool_results: list[dict[str, Any]] | None = None,
        thinking_override: bool | None = None,
    ) -> tuple[dict[str, Any], bool, str]:
        if not image_paths:
            raise ValueError("At least one image is required")
        if not self._inference_lock.acquire(timeout=self.inference_wait_seconds):
            raise TimeoutError("Runtime is busy")
        try:
            self._load()
            return self._generate(
                task,
                image_paths,
                tools or [],
                tool_results or [],
                thinking_override,
            )
        finally:
            self._inference_lock.release()

    def _generate(
        self,
        task: str,
        image_paths: list[Path],
        tools: list[str],
        tool_results: list[dict[str, Any]],
        thinking_override: bool | None = None,
    ) -> tuple[dict[str, Any], bool, str]:
        torch = self._torch
        processor = self._processor
        model = self._model
        enable_thinking = (
            self.enable_thinking if thinking_override is None else thinking_override
        )
        max_decoded_pixels = _env_int(
            "MODEL_RUNTIME_MAX_DECODED_PIXELS",
            DEFAULT_MAX_IMAGE_PIXELS,
            65_536,
            MAX_ALLOWED_DECODED_PIXELS,
        )
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
        resize_size = {
            "shortest_edge": self.image_pixels,
            "longest_edge": self.image_pixels,
        }
        images = []
        try:
            for path in image_paths:
                # Match training and evaluation: the processor owns resizing
                # after the original image passes the decoded-dimension guard.
                images.append(_load_rgb_image(path, max_decoded_pixels))
            content = [{"type": "image", "image": image} for image in images]
            content.append(
                {
                    "type": "text",
                    "text": _task_prompt(task) + _tool_prompt(tools, tool_results),
                }
            )
            messages = [{"role": "user", "content": content}]
            text = processor.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=enable_thinking,
            )
            inputs = processor(
                text=[text],
                images=images,
                return_tensors="pt",
                size=resize_size,
            )
            inputs = {
                key: value.to("cuda") if torch.is_tensor(value) else value
                for key, value in inputs.items()
            }
            with torch.inference_mode():
                max_new = (
                    self.thinking_max_new_tokens
                    if enable_thinking
                    else self.max_new_tokens
                )
                generated = model.generate(
                    **inputs,
                    max_new_tokens=max_new,
                    do_sample=False,
                )
            generated = generated[:, inputs["input_ids"].shape[1] :]
            raw = processor.batch_decode(
                generated,
                skip_special_tokens=True,
            )[0]
            answer, thinking = _strip_thinking(raw)
            truncated = (
                generated.shape[1] >= max_new
                and not raw.rstrip().endswith("}")
            )
            torch.cuda.synchronize()
            del inputs, generated
            try:
                result = _parse_output(answer, task, tools)
            except ValueError:
                if not enable_thinking:
                    raise
                # The frozen research adapter may emit useful reasoning without a
                # final structured JSON. Retry compactly instead of failing after
                # the doctor deliberately requested the slower path.
                thinking = (thinking or answer).strip()
                text = processor.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                    enable_thinking=False,
                )
                inputs = processor(
                    text=[text],
                    images=images,
                    return_tensors="pt",
                    size=resize_size,
                )
                inputs = {
                    key: value.to("cuda") if torch.is_tensor(value) else value
                    for key, value in inputs.items()
                }
                with torch.inference_mode():
                    generated = model.generate(
                        **inputs,
                        max_new_tokens=self.max_new_tokens,
                        do_sample=False,
                    )
                generated = generated[:, inputs["input_ids"].shape[1] :]
                raw = processor.batch_decode(
                    generated,
                    skip_special_tokens=True,
                )[0]
                answer, _ = _strip_thinking(raw)
                result = _parse_output(answer, task, tools)
                truncated = (
                    generated.shape[1] >= self.max_new_tokens
                    and not raw.rstrip().endswith("}")
                )
                thinking = f"{thinking}\n\n[thinking fallback used]".strip()
            return result, truncated, thinking
        finally:
            for image in images:
                image.close()

    def peak_memory(self) -> tuple[float | None, float | None]:
        if self._torch is None or not self._torch.cuda.is_initialized():
            return None, None
        return (
            self._torch.cuda.max_memory_allocated() / 1024**3,
            self._torch.cuda.max_memory_reserved() / 1024**3,
        )


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_runtime: QwenRuntime | None = None
_runtime_lock = threading.Lock()


def _get_runtime() -> QwenRuntime:
    global _runtime
    if _runtime is not None:
        return _runtime
    with _runtime_lock:
        if _runtime is None:
            model_dir, adapter_dir = _paths()
            _runtime = QwenRuntime(
                model_dir,
                adapter_dir,
                image_pixels=_env_int(
                    "MODEL_RUNTIME_IMAGE_PIXELS",
                    DEFAULT_IMAGE_PIXELS,
                    4_096,
                    451_584,
                ),
                max_new_tokens=_env_int(
                    "MODEL_RUNTIME_MAX_NEW_TOKENS",
                    DEFAULT_MAX_NEW_TOKENS,
                    8,
                    128,
                ),
                enable_thinking=_thinking_enabled(),
                thinking_max_new_tokens=_env_int(
                    "MODEL_RUNTIME_THINKING_MAX_NEW_TOKENS",
                    DEFAULT_THINKING_MAX_NEW_TOKENS,
                    64,
                    8192,
                ),
                inference_wait_seconds=_env_int(
                    "MODEL_RUNTIME_INFERENCE_WAIT_SECONDS",
                    35,
                    1,
                    120,
                ),
            )
    return _runtime


@app.get("/health")
def health() -> dict:
    model_dir, adapter_dir = _paths()
    model_ready = model_dir.is_dir()
    adapter_ready = _adapter_ready(adapter_dir)
    return {
        "status": "ok" if model_ready and adapter_ready else "degraded",
        "service": "model/runtime",
        "gpu_required": True,
        "model": {
            "name": "Qwen3.5-4B",
            "path": str(model_dir),
            "status": _path_status(model_dir),
        },
        "adapter": {
            "path": str(adapter_dir),
            "status": "ready" if adapter_ready else "missing",
        },
        "inference": {
            "endpoint": "/v1/judge",
            "status": "ready" if model_ready and adapter_ready else "degraded",
            "loaded": bool(_runtime and _runtime.loaded),
            "task": DEFAULT_TASK,
            "thinking": _thinking_enabled(),
            "requires_human_review": True,
        },
        "decision_model": {
            "name": "Intern-Decision-4B",
            "status": "disabled",
        },
    }


@app.get("/v1/models")
def models() -> dict:
    payload = health()
    return {
        "models": [
            {
                "role": "qwen_judgment",
                "name": payload["model"]["name"],
                "status": payload["model"]["status"],
            },
            {
                "role": "adapter",
                "name": payload["adapter"]["path"],
                "status": payload["adapter"]["status"],
            },
            {
                "role": "decision",
                "name": payload["decision_model"]["name"],
                "status": payload["decision_model"]["status"],
            },
        ]
    }


@app.post("/v1/judge", response_model=JudgeResponse)
def judge(payload: JudgeRequest, request: Request) -> JudgeResponse:
    started = time.perf_counter()
    if payload.task not in TASK_LABELS:
        raise HTTPException(status_code=422, detail="Unsupported judgment task")
    if not payload.case.images:
        raise HTTPException(status_code=422, detail="At least one image is required")
    if len(payload.case.images) > _env_int(
        "MODEL_RUNTIME_MAX_IMAGES",
        DEFAULT_MAX_IMAGES,
        1,
        MAX_ALLOWED_IMAGES,
    ):
        raise HTTPException(status_code=413, detail="Too many images")

    internal_token = os.environ.get("MODEL_RUNTIME_INTERNAL_TOKEN", "")
    supplied_token = request.headers.get("X-Internal-Service-Token", "")
    if internal_token and supplied_token != internal_token:
        raise HTTPException(status_code=401, detail="Invalid internal service token")

    image_paths = [_resolve_case_image(image) for image in payload.case.images]
    runtime = _get_runtime()
    # Loading is intentionally separate so validation and path checks remain
    # cheap and do not occupy the GPU worker for malformed requests.
    try:
        runtime.load()
    except Exception as exc:
        LOG.exception("runtime_load_failed")
        raise HTTPException(
            status_code=503,
            detail=f"Model runtime unavailable: {type(exc).__name__}",
        ) from exc
    try:
        result, truncated, thinking = runtime.judge(
            payload.task,
            image_paths,
            payload.tools,
            payload.tool_results,
            payload.enable_thinking,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        LOG.exception("judgment_failed")
        raise HTTPException(
            status_code=503,
            detail=f"Model inference unavailable: {type(exc).__name__}",
        ) from exc

    common = dict(
        task=payload.task,
        model=runtime.model_dir.name,
        adapter_sha256=runtime._adapter_sha256,
        latency_ms=int((time.perf_counter() - started) * 1000),
        generated_at=datetime.now(UTC).isoformat(),
        truncated=truncated,
        thinking=thinking[:2000],
        thinking_mode=(
            _thinking_enabled()
            if payload.enable_thinking is None
            else payload.enable_thinking
        ),
            thinking_fallback_used="[thinking fallback used]" in thinking,
        peak_allocated_gib=runtime.peak_memory()[0],
        peak_reserved_gib=runtime.peak_memory()[1],
    )
    if result["status"] == "tool_call":
        return JudgeResponse(status="tool_call", tool_call=JudgeToolCall(**result["tool_call"]), **common)
    return JudgeResponse(status="result", result=JudgeResult(**result["result"]), **common)
