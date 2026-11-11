from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Callable, Sequence

from .models import FaceScore, ReferenceImage, Scan, SearchResult

Encoding = object
Encoder = Callable[[bytes], Sequence[Encoding]]
Distance = Callable[[Encoding, Encoding], float]


class FaceSearchAdapter:
    """Expose face-search similarity scores without making match decisions."""

    def __init__(
        self,
        name: str = "face-search",
        *,
        encoder: Encoder | None = None,
        distance: Distance | None = None,
    ) -> None:
        self.name = name
        self._encoder = encoder or _default_encoder
        self._distance = distance or _default_distance
        self._reference_cache: dict[Path, tuple[Encoding, ...]] = {}

    def search(
        self, gallery: Sequence[ReferenceImage], scan: Scan
    ) -> SearchResult:
        try:
            unknown = tuple(self._encoder(scan.path.read_bytes()))
            if not unknown:
                return SearchResult(has_face=False)
            by_identity: dict[str, list[Encoding]] = defaultdict(list)
            for reference in gallery:
                encodings = self._reference_cache.get(reference.path)
                if encodings is None:
                    encodings = tuple(self._encoder(reference.path.read_bytes()))
                    self._reference_cache[reference.path] = encodings
                if not encodings:
                    return SearchResult(
                        has_face=False,
                        error=f"reference image has no face: {reference.id}",
                    )
                by_identity[reference.identity_id].extend(encodings)
            scores = tuple(
                FaceScore(
                    identity_id=identity_id,
                    score=max(
                        1.0 - self._distance(known, observed)
                        for known in known_encodings
                        for observed in unknown
                    ),
                )
                for identity_id, known_encodings in sorted(by_identity.items())
            )
            return SearchResult(has_face=True, scores=scores)
        except Exception as exc:
            return SearchResult(
                has_face=False,
                error=f"{type(exc).__name__}: {exc}",
            )


def _default_encoder(content: bytes) -> Sequence[Encoding]:
    from app.services.ai_service import get_face_encodings

    return get_face_encodings(content)


def _default_distance(known: Encoding, observed: Encoding) -> float:
    import face_recognition

    return float(face_recognition.face_distance([known], observed)[0])
