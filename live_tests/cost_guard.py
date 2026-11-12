"""Observe real HTTP responses and enforce conservative pre-request limits.

This is a forwarding transport guard, not a fake provider. Pricing assumptions
must be reviewed if the allowed models or published standard rates change.
"""
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

RATES = {
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "gpt-4o-mini-2024-07-18": (Decimal("0.15"), Decimal("0.60")),
}


class LiveBudgetExceeded(RuntimeError):
    pass


@dataclass
class CallBudget:
    model: str
    max_calls: int = 2
    budget_usd: Decimal = Decimal("0.05")
    output_limit: int = 2000
    reserved_usd: Decimal = field(default=Decimal(0), init=False)
    calls: list = field(default_factory=list, init=False)
    stop_reason: str = field(default="", init=False)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), init=False)
    lock: object = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self):
        self.budget_usd = Decimal(str(self.budget_usd))
        if self.model not in RATES:
            raise ValueError("Live tests allow only gpt-4o-mini or its priced snapshot")
        if isinstance(self.max_calls, bool) or not isinstance(self.max_calls, int) or not 1 <= self.max_calls <= 3:
            raise ValueError("Paid calls per run must be between 1 and 3")
        if not self.budget_usd.is_finite() or not 0 < self.budget_usd <= Decimal("0.10"):
            raise ValueError("Estimated run budget must be positive and at most $0.10")
        if isinstance(self.output_limit, bool) or not isinstance(self.output_limit, int) or not 32 <= self.output_limit <= 2000:
            raise ValueError("Output cap must be between 32 and 2000 tokens")

    def _blocked(self, reason):
        self.stop_reason = reason
        raise LiveBudgetExceeded(reason)

    def reserve(self, request):
        with self.lock:
            if (request.method != "POST" or request.url.scheme != "https"
                    or request.url.host != "api.openai.com" or request.url.path != "/v1/chat/completions"
                    or request.url.port not in (None, 443)):
                self._blocked("Only the standard OpenAI chat-completions endpoint is allowed")
            body = json.loads(request.content)
            if body.get("model") != self.model:
                self._blocked("Request model differs from the allowed, priced model")
            if body.get("stream") or body.get("tools") or body.get("n", 1) != 1:
                self._blocked("Live budget covers one non-streaming text completion without tools")
            if any(name in body for name in ("audio", "modalities", "web_search_options", "prediction")):
                self._blocked("Additional billed modalities/features are not covered by this test budget")
            if body.get("service_tier", "default") not in (None, "default"):
                self._blocked("Only standard service-tier pricing is covered")
            limit = body.get("max_tokens")
            if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= self.output_limit:
                self._blocked("Request must have an explicit max_tokens within the output cap")
            if "max_completion_tokens" in body:
                self._blocked("Use the app's single max_tokens limit, not conflicting token limits")
            messages = body.get("messages")
            if not isinstance(messages, list) or not messages or not all(
                    isinstance(m, dict) and isinstance(m.get("content"), str) for m in messages):
                self._blocked("Only plain-text messages are covered by this budget")
            if len(self.calls) >= self.max_calls:
                self._blocked("Paid request-count limit reached; no further request was sent")
            # GPT-4o's byte-based tokenizer cannot need more text tokens than
            # UTF-8 bytes. Add a deliberately large framing allowance; reserve
            # full output, even if the actual answer will be much shorter.
            input_bound = len(request.content) + 8192
            input_rate, output_rate = RATES[self.model]
            reserve = (Decimal(input_bound) * input_rate + Decimal(limit) * output_rate) / 1_000_000
            if self.reserved_usd + reserve > self.budget_usd:
                self._blocked("Conservative estimated dollar budget reached; request was not sent")
            event = dict(number=len(self.calls) + 1, model=self.model, reserved_input_tokens=input_bound,
                         max_output_tokens=limit, reserved_usd=float(reserve), http_status=None,
                         input_tokens=None, output_tokens=None, estimated_usage_usd=None)
            self.calls.append(event)
            self.reserved_usd += reserve
            return event

    def forwarding_handler(self, original):
        def handle(transport, request):
            event = self.reserve(request)
            try:
                response = original(transport, request)  # Actual provider I/O.
                event["http_status"] = response.status_code
                response.read()
                try:
                    decoded = response.json()
                    usage = decoded.get("usage", {})
                    if isinstance(decoded.get("model"), str):
                        event["response_model"] = decoded["model"]
                    if response.status_code >= 400:
                        code = (decoded.get("error") or {}).get("code")
                        if isinstance(code, str) and len(code) <= 64 and all(c.isalnum() or c == "_" for c in code):
                            event["error_code"] = code
                    incoming, outgoing = usage.get("prompt_tokens"), usage.get("completion_tokens")
                    if (isinstance(incoming, int) and not isinstance(incoming, bool) and incoming >= 0
                            and isinstance(outgoing, int) and not isinstance(outgoing, bool) and outgoing >= 0):
                        a, b = RATES[self.model]
                        event.update(input_tokens=incoming, output_tokens=outgoing,
                                     estimated_usage_usd=float((incoming * a + outgoing * b) / 1_000_000))
                except (ValueError, AttributeError):
                    pass
                return response
            except Exception:
                # A timeout may still have incurred a charge. Never refund its reservation.
                event["transport_error"] = True
                raise
        return handle

    def report(self):
        known = bool(self.calls) and all(c["estimated_usage_usd"] is not None for c in self.calls)
        return dict(source="opt-in real OpenAI requests; no stub responses", model=self.model,
                    started_at=self.started_at,
                    max_paid_attempts=self.max_calls, paid_attempts=len(self.calls),
                    conservative_budget_usd=float(self.budget_usd), reserved_usd=float(self.reserved_usd),
                    estimated_usage_usd=sum(c["estimated_usage_usd"] for c in self.calls) if known else None,
                    stop_reason=self.stop_reason or None, calls=self.calls,
                    caveat="Estimates use published base rates, not an invoice or account-wide spending cap")

    def write_report(self, path, outcomes):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(dict(self.report(), finished_at=datetime.now(timezone.utc).isoformat(), tests=outcomes), indent=2) + "\n")
