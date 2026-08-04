from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from app.acquisition.interfaces import PiClient, PiClientError
from app.config.models import AppConfig
from app.domain.models import AcquisitionBatch, PiEvent
from app.validation.tags import TagAuthorizer


class PiAfSdkClient(PiClient):
    """Windows-only PI AF SDK adapter, loaded lazily to keep tests SDK-independent."""

    def __init__(self, config: AppConfig) -> None:
        if not config.pi_system.data_archive:
            raise PiClientError("PI Data Archive must be configured for PI AF SDK access")
        self._config = config
        self._authorizer = TagAuthorizer(config)
        self._server: Any | None = None
        self._sdk: dict[str, Any] | None = None

    def fetch_current(self, tags: Sequence[str]) -> AcquisitionBatch:
        requested = self._authorizer.validate(tags)
        server, sdk = self._connection()
        acquired_at = datetime.now(timezone.utc)
        try:
            events = [self._to_event(tag, sdk["PIPoint"].FindPIPoint(server, tag).CurrentValue()) for tag in requested]
        except Exception as exc:  # SDK exception classes vary by installed AF SDK version.
            raise PiClientError("PI AF SDK current-value query failed") from exc
        return AcquisitionBatch(
            acquired_at=acquired_at,
            query_mode="current",
            source="pi_af_sdk",
            events=events,
        )

    def fetch_recorded(self, tags: Sequence[str], start: datetime, end: datetime) -> AcquisitionBatch:
        requested = self._authorizer.validate(tags)
        if end < start:
            raise ValueError("Historical end must not precede start")
        server, sdk = self._connection()
        acquired_at = datetime.now(timezone.utc)
        events: list[PiEvent] = []
        try:
            for tag in requested:
                point = sdk["PIPoint"].FindPIPoint(server, tag)
                time_range = sdk["AFTimeRange"](start.isoformat(), end.isoformat())
                values = point.RecordedValues(
                    time_range,
                    sdk["AFBoundaryType"].Inside,
                    None,
                    False,
                    self._config.acquisition.maximum_events_per_query,
                )
                events.extend(self._to_event(tag, value) for value in values)
        except Exception as exc:
            raise PiClientError("PI AF SDK recorded-values query failed") from exc
        return AcquisitionBatch(
            acquired_at=acquired_at,
            query_mode="recorded",
            source="pi_af_sdk",
            events=events,
        )

    def _connection(self) -> tuple[Any, dict[str, Any]]:
        if self._server is not None and self._sdk is not None:
            return self._server, self._sdk
        try:
            import pythonnet  # type: ignore[import-not-found]

            # PI AF SDK is a .NET Framework SDK. The runtime must be selected
            # before importing clr; pythonnet otherwise prefers CoreCLR.
            pythonnet.load("netfx")
            import clr  # type: ignore[import-not-found]

            clr.AddReference(str(self._assembly_path()))
            from OSIsoft.AF.Data import AFBoundaryType  # type: ignore[import-not-found]
            from OSIsoft.AF.PI import PIPoint, PIServers  # type: ignore[import-not-found]
            from OSIsoft.AF.Time import AFTimeRange  # type: ignore[import-not-found]
        except Exception as exc:
            raise PiClientError(
                "PI AF SDK or pythonnet is unavailable. Install the approved AF SDK and optional Python dependency."
            ) from exc
        try:
            servers = PIServers()
            server = servers[self._config.pi_system.data_archive]
            server.Connect()
        except Exception as exc:
            raise PiClientError("Could not connect to the configured PI Data Archive using Windows authentication") from exc
        self._server = server
        self._sdk = {"PIPoint": PIPoint, "AFBoundaryType": AFBoundaryType, "AFTimeRange": AFTimeRange}
        return server, self._sdk

    def _assembly_path(self) -> Path:
        configured = self._config.pi_system.af_sdk_assembly_path
        candidates = [
            Path(configured) if configured else None,
            Path(r"C:\Program Files (x86)\PIPC\AF\PublicAssemblies\4.0\OSIsoft.AFSDK.dll"),
            Path(r"C:\Program Files\PIPC\AF\PublicAssemblies\4.0\OSIsoft.AFSDK.dll"),
            Path(r"C:\Program Files\AVEVA\PI System\AF\PublicAssemblies\4.0\OSIsoft.AFSDK.dll"),
        ]
        for candidate in candidates:
            if candidate and candidate.is_file():
                return candidate
        raise PiClientError("OSIsoft.AFSDK.dll was not found in the configured or standard Windows locations")

    def _to_event(self, tag_name: str, af_value: Any) -> PiEvent:
        timestamp = self._to_datetime(getattr(af_value, "Timestamp", None))
        value = getattr(af_value, "Value", None)
        status = getattr(af_value, "Status", None)
        return PiEvent(
            tag_name=tag_name,
            pi_event_timestamp=timestamp,
            value=self._safe_value(value),
            quality=str(status) if status is not None else None,
            questionable=bool(getattr(af_value, "IsQuestionable", False)),
            substituted=bool(getattr(af_value, "IsSubstituted", False)),
            unit=None,
            source="pi_af_sdk",
        )

    @staticmethod
    def _safe_value(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    @staticmethod
    def _to_datetime(value: Any) -> datetime:
        if value is None:
            raise PiClientError("PI AF SDK returned an event without timestamp")
        candidate = getattr(value, "UtcTime", value)
        if isinstance(candidate, datetime):
            return candidate if candidate.tzinfo else candidate.replace(tzinfo=timezone.utc)
        try:
            text = candidate.ToString("O")
            return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
        except Exception as exc:
            raise PiClientError("PI AF SDK returned an unsupported timestamp") from exc
