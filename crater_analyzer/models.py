from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot


def distance(a: tuple[float, float] | None, b: tuple[float, float] | None) -> float | None:
    if a is None or b is None:
        return None
    return hypot(a[0] - b[0], a[1] - b[1])


@dataclass
class CraterRecord:
    index: int
    expected_frame: int | None = None
    expected_x: float | None = None
    expected_y: float | None = None
    visible: bool = False
    missing: bool = False
    rim_present: bool | None = None
    center_x: float | None = None
    center_y: float | None = None
    measurement_frame: int | None = None
    inner_a: tuple[float, float] | None = None
    inner_b: tuple[float, float] | None = None
    outer_a: tuple[float, float] | None = None
    outer_b: tuple[float, float] | None = None
    notes: str = ""
    auto_score: float | None = None
    flags: list[str] = field(default_factory=list)

    @property
    def inner_diameter_px(self) -> float | None:
        return distance(self.inner_a, self.inner_b)

    @property
    def outer_diameter_px(self) -> float | None:
        return distance(self.outer_a, self.outer_b)

    def set_center(self, point: tuple[float, float], frame: int) -> None:
        self.center_x, self.center_y = point
        self.measurement_frame = frame
        self.visible = True
        self.missing = False

    def set_missing(self) -> None:
        self.visible = False
        self.missing = True
        self.rim_present = None
        self.center_x = None
        self.center_y = None
        self.inner_a = None
        self.inner_b = None
        self.outer_a = None
        self.outer_b = None

    def expected_point(self) -> tuple[float, float] | None:
        if self.expected_x is None or self.expected_y is None:
            return None
        return self.expected_x, self.expected_y

    def center_point(self) -> tuple[float, float] | None:
        if self.center_x is None or self.center_y is None:
            return None
        return self.center_x, self.center_y

    def status_text(self) -> str:
        if self.missing:
            return "missing"
        if self.visible:
            return "visible"
        return "unreviewed"
