"""Lazy official TypeSafe SDK adapter for Jev judgments.

Jev is not an agent: this module only asks typed questions and normalizes
answers. Credentials come from ToolContext/KeyStore (`typesafe`), never argv.
The SDK is imported on first use so shell startup, model listing, and ordinary
chats make no TypeSafe network requests.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

LOGGER = logging.getLogger("ambxst.jev")

JEV_MODEL = "jev-latest"
KEYSTORE_PROVIDER = "typesafe"

STATUS_OK = "ok"
STATUS_MISSING_KEY = "missing_key"
STATUS_MISSING_SDK = "missing_sdk"
STATUS_TIMEOUT = "timeout"
STATUS_CANCELLED = "cancelled"
STATUS_UNAVAILABLE = "unavailable"
STATUS_ERROR = "error"
STATUS_MALFORMED = "malformed"
STATUS_SKIPPED = "skipped"

KIND_CHOICE = "choice"
KIND_NOUL = "noul"
KIND_SCORE = "score"

_CLIENT_FACTORY = None


def set_client_factory(factory):
    """Inject a test double. `factory(api_key, timeout_s, max_retries)` -> client."""
    global _CLIENT_FACTORY
    _CLIENT_FACTORY = factory


def reset_client_factory():
    set_client_factory(None)


@dataclass
class NormalizedAnswer:
    kind: str
    value: object = None
    confidence: float | None = None
    probabilities: dict = field(default_factory=dict)
    noul: float | None = None
    score: float | None = None
    choice: str | None = None


@dataclass
class Judgment:
    status: str
    answers: dict = field(default_factory=dict)
    latency_ms: float = 0.0
    error: str = ""
    request_id: str = ""

    @property
    def ok(self):
        return self.status == STATUS_OK


def _cancelled(ctx):
    return bool(ctx is not None and callable(getattr(ctx, "cancelled", None)) and ctx.cancelled())


def _get_key(ctx):
    if ctx is None:
        return ""
    getter = getattr(ctx, "get_key", None)
    if callable(getter):
        try:
            return getter(KEYSTORE_PROVIDER) or ""
        except Exception:
            return ""
    keys = getattr(ctx, "api_keys", None) or {}
    return keys.get(KEYSTORE_PROVIDER) or ""


def _import_sdk():
    try:
        import typesafe_sdk

        return typesafe_sdk
    except ImportError:
        return None


def sdk_available():
    if _CLIENT_FACTORY is not None:
        return True
    return _import_sdk() is not None


def _to_sdk_questions(sdk, questions):
    if not questions:
        return questions
    choice_cls = getattr(sdk, "Choice", None)
    noul_cls = getattr(sdk, "Noul", None)
    score_cls = getattr(sdk, "Score", None)
    out = {}
    for name, question in questions.items():
        if not isinstance(question, dict):
            out[name] = question
            continue
        kind = question.get("type")
        instructions = question.get("instructions")
        criteria = question.get("criteria")
        if kind == KIND_CHOICE and choice_cls is not None:
            out[name] = choice_cls(instructions=instructions, criteria=criteria)
        elif kind == KIND_NOUL and noul_cls is not None:
            out[name] = noul_cls(instructions=instructions, criteria=criteria)
        elif kind == KIND_SCORE and score_cls is not None:
            out[name] = score_cls(instructions=instructions, criteria=criteria)
        else:
            out[name] = question
    return out


def _float(value, default=None):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _prob_map(raw):
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key, value in raw.items():
        number = _float(value)
        if number is None:
            continue
        out[str(key)] = number
    return out


def normalize_choice(answer):
    if answer is None:
        return None
    choice = getattr(answer, "choice", None)
    if choice is None and isinstance(answer, dict):
        choice = answer.get("choice")
    if choice is None or str(choice).strip() == "":
        return None
    confidence = getattr(answer, "confidence", None)
    if confidence is None and isinstance(answer, dict):
        confidence = answer.get("confidence")
    probabilities = getattr(answer, "probabilities", None)
    if probabilities is None and isinstance(answer, dict):
        probabilities = answer.get("probabilities")
    return NormalizedAnswer(
        kind=KIND_CHOICE,
        value=str(choice),
        choice=str(choice),
        confidence=_float(confidence),
        probabilities=_prob_map(probabilities),
    )


def normalize_noul(answer):
    if answer is None:
        return None
    noul = getattr(answer, "noul", None)
    if noul is None and isinstance(answer, dict):
        noul = answer.get("noul")
    number = _float(noul)
    if number is None:
        return None
    return NormalizedAnswer(
        kind=KIND_NOUL,
        value=number,
        noul=number,
        confidence=None,
        probabilities={"true": number, "false": 1.0 - number},
    )


def normalize_score(answer):
    if answer is None:
        return None
    score = getattr(answer, "score", None)
    if score is None and isinstance(answer, dict):
        score = answer.get("score")
    number = _float(score)
    if number is None:
        return None
    confidence = getattr(answer, "confidence", None)
    if confidence is None and isinstance(answer, dict):
        confidence = answer.get("confidence")
    probabilities = getattr(answer, "probabilities", None)
    if probabilities is None and isinstance(answer, dict):
        probabilities = answer.get("probabilities")
    return NormalizedAnswer(
        kind=KIND_SCORE,
        value=number,
        score=number,
        confidence=_float(confidence),
        probabilities=_prob_map(probabilities),
    )


def _answers_from_mapping(mapping, normalizer):
    out = {}
    if not mapping:
        return out
    items = mapping.items() if isinstance(mapping, dict) else []
    for name, raw in items:
        parsed = normalizer(raw)
        if parsed is not None:
            out[str(name)] = parsed
    return out


def normalize_response(response):
    """Turn an SDK (or fake) System One response into plain Python data."""
    if response is None:
        return None
    answers = {}
    choices = getattr(response, "choices", None)
    if choices is None and isinstance(response, dict):
        choices = response.get("choices")
    nouls = getattr(response, "nouls", None)
    if nouls is None and isinstance(response, dict):
        nouls = response.get("nouls")
    scores = getattr(response, "scores", None)
    if scores is None and isinstance(response, dict):
        scores = response.get("scores")
    answers.update(_answers_from_mapping(choices, normalize_choice))
    answers.update(_answers_from_mapping(nouls, normalize_noul))
    answers.update(_answers_from_mapping(scores, normalize_score))
    grouped = getattr(response, "answers", None)
    if grouped is None and isinstance(response, dict):
        grouped = response.get("answers")
    if isinstance(grouped, dict):
        for name, raw in grouped.items():
            if name in answers:
                continue
            kind = getattr(raw, "type", None) or (raw.get("type") if isinstance(raw, dict) else None)
            if kind == KIND_CHOICE or hasattr(raw, "choice") or (isinstance(raw, dict) and "choice" in raw):
                parsed = normalize_choice(raw)
            elif kind == KIND_NOUL or hasattr(raw, "noul") or (isinstance(raw, dict) and "noul" in raw):
                parsed = normalize_noul(raw)
            elif kind == KIND_SCORE or hasattr(raw, "score") or (isinstance(raw, dict) and "score" in raw):
                parsed = normalize_score(raw)
            else:
                parsed = None
            if parsed is not None:
                answers[str(name)] = parsed
    if not answers:
        return None
    request_id = getattr(response, "request_id", None)
    if request_id is None and isinstance(response, dict):
        request_id = response.get("request_id") or ""
    return str(request_id or ""), answers


def _classify_exception(exc):
    name = type(exc).__name__
    message = str(exc) or name
    if isinstance(exc, TimeoutError) or name in {"TypeSafeAPITimeoutError", "TimeoutException"}:
        return STATUS_TIMEOUT, message
    if name in {"TypeSafeAuthenticationError", "AuthenticationError"}:
        return STATUS_UNAVAILABLE, "unauthorized"
    if name in {"TypeSafeAPIConnectionError", "APIConnectionError"}:
        return STATUS_UNAVAILABLE, message
    if name in {"TypeSafeError", "TypeSafeAPIError"}:
        status = getattr(exc, "status", None)
        if status in (401, 403):
            return STATUS_UNAVAILABLE, "unauthorized"
        if status in (408, 429) or (isinstance(status, int) and status >= 500):
            return STATUS_UNAVAILABLE, message
        return STATUS_ERROR, message
    return STATUS_ERROR, message


def _build_official_client(sdk, api_key, timeout_s, max_retries):
    retry = None
    retry_cls = getattr(sdk, "RetryPolicy", None)
    if retry_cls is not None:
        retry = retry_cls(
            max_retries=max(0, int(max_retries)),
            backoff_initial=0.05,
            backoff_max=0.2,
            timeout=float(timeout_s),
            api_timeout_error=False,
        )
    return sdk.TypeSafeClient(
        api_key=api_key,
        model=JEV_MODEL,
        timeout=float(timeout_s),
        retry=retry,
    )


def _client_for(ctx, api_key, timeout_s, max_retries):
    cached = getattr(ctx, "_jev_sdk_client", None) if ctx is not None else None
    if cached is not None:
        return cached
    if _CLIENT_FACTORY is not None:
        client = _CLIENT_FACTORY(api_key, timeout_s, max_retries)
    else:
        sdk = _import_sdk()
        if sdk is None:
            return None
        client = _build_official_client(sdk, api_key, timeout_s, max_retries)
    if ctx is not None:
        ctx._jev_sdk_client = client
    return client


def ask(ctx, state, questions, timeout_s=1.5, max_retries=1):
    """Ask Jev about `state`. Returns a Judgment; never raises to callers."""
    started = time.monotonic()

    def done(status, error="", answers=None, request_id=""):
        latency = (time.monotonic() - started) * 1000.0
        return Judgment(
            status=status,
            answers=answers or {},
            latency_ms=latency,
            error=error,
            request_id=request_id,
        )

    if _cancelled(ctx):
        return done(STATUS_CANCELLED, "cancelled")
    if not questions:
        return done(STATUS_MALFORMED, "empty questions")
    if state is None:
        return done(STATUS_MALFORMED, "missing state")

    api_key = _get_key(ctx)
    if _CLIENT_FACTORY is None and not api_key:
        return done(STATUS_MISSING_KEY, "no typesafe API key")
    if _CLIENT_FACTORY is None and _import_sdk() is None:
        return done(STATUS_MISSING_SDK, "typesafe_sdk is not installed")

    try:
        client = _client_for(ctx, api_key, timeout_s, max_retries)
    except Exception as exc:
        status, message = _classify_exception(exc)
        LOGGER.info("jev client init failed status=%s", status)
        return done(status, message)
    if client is None:
        return done(STATUS_MISSING_SDK, "typesafe_sdk is not installed")

    sdk = _import_sdk() if _CLIENT_FACTORY is None else None
    payload = _to_sdk_questions(sdk, questions) if sdk is not None else questions
    try:
        if hasattr(client, "system_one"):
            response = client.system_one(state=state, questions=payload)
        elif callable(client):
            response = client(state, payload)
        else:
            return done(STATUS_UNAVAILABLE, "client cannot ask system_one")
    except Exception as exc:
        status, message = _classify_exception(exc)
        LOGGER.info("jev request failed status=%s", status)
        return done(status, message)

    if _cancelled(ctx):
        return done(STATUS_CANCELLED, "cancelled")

    parsed = normalize_response(response)
    if parsed is None:
        return done(STATUS_MALFORMED, "malformed answers")
    request_id, answers = parsed
    expected = set(questions)
    if expected and not expected.intersection(answers):
        return done(STATUS_MALFORMED, "malformed answers", request_id=request_id)
    return done(STATUS_OK, answers=answers, request_id=request_id)


class FakeChoice:
    def __init__(self, choice, confidence=0.9, probabilities=None):
        self.choice = choice
        self.confidence = confidence
        self.probabilities = probabilities if probabilities is not None else {choice: confidence}


class FakeNoul:
    def __init__(self, noul):
        self.noul = float(noul)


class FakeScore:
    def __init__(self, score, confidence=0.9, probabilities=None):
        self.score = float(score)
        self.confidence = confidence
        self.probabilities = probabilities or {}


class FakeResponse:
    def __init__(self, choices=None, nouls=None, scores=None, request_id="fake"):
        self.choices = choices or {}
        self.nouls = nouls or {}
        self.scores = scores or {}
        self.answers = {}
        self.answers.update(self.choices)
        self.answers.update(self.nouls)
        self.answers.update(self.scores)
        self.request_id = request_id


class FakeClient:
    """Deterministic test double with the TypeSafeClient.system_one surface."""

    def __init__(self, response=None, error=None, delay_s=0.0):
        self.response = response
        self.error = error
        self.delay_s = delay_s
        self.calls = []

    def system_one(self, state, questions, **_kwargs):
        self.calls.append({"state": state, "questions": questions})
        if self.delay_s:
            time.sleep(self.delay_s)
        if self.error is not None:
            raise self.error
        if callable(self.response):
            return self.response(state, questions)
        return self.response
