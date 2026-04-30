from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class VideoInfo:
    path: Path
    frame_count: int
    fps: float
    width: int
    height: int


class VideoReader:
    def __init__(self) -> None:
        self._capture: cv2.VideoCapture | None = None
        self.info: VideoInfo | None = None
        self._last_index: int | None = None
        self._last_frame: np.ndarray | None = None

    def open(self, path: str | Path) -> VideoInfo:
        self.close()
        video_path = Path(path)
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise RuntimeError(f"Could not open video: {video_path}")

        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))

        self._capture = capture
        self.info = VideoInfo(video_path, frame_count, fps, width, height)
        self._last_index = None
        self._last_frame = None
        return self.info

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
        self._capture = None
        self.info = None
        self._last_index = None
        self._last_frame = None

    def read(self, index: int) -> np.ndarray:
        if self._capture is None or self.info is None:
            raise RuntimeError("No video is open.")
        index = max(0, min(index, self.info.frame_count - 1))
        if self._last_index == index and self._last_frame is not None:
            return self._last_frame.copy()

        self._capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = self._capture.read()
        if not ok or frame is None:
            raise RuntimeError(f"Could not read frame {index}.")

        self._last_index = index
        self._last_frame = frame
        return frame.copy()


def adjusted_frame(
    frame_bgr: np.ndarray,
    brightness: int,
    contrast: float,
    gamma: float,
    use_clahe: bool,
    sharpen: bool,
) -> np.ndarray:
    frame = cv2.convertScaleAbs(frame_bgr, alpha=contrast, beta=brightness)

    if use_clahe:
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        lightness, a_channel, b_channel = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        lightness = clahe.apply(lightness)
        frame = cv2.cvtColor(cv2.merge((lightness, a_channel, b_channel)), cv2.COLOR_LAB2BGR)

    if abs(gamma - 1.0) > 0.01:
        inv_gamma = 1.0 / max(gamma, 0.05)
        table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype(
            "uint8"
        )
        frame = cv2.LUT(frame, table)

    if sharpen:
        blurred = cv2.GaussianBlur(frame, (0, 0), 1.0)
        frame = cv2.addWeighted(frame, 1.5, blurred, -0.5, 0)

    return frame


def detect_crater_candidate(
    frame_bgr: np.ndarray,
    expected: tuple[float, float] | None,
    search_radius: int = 140,
) -> tuple[float, float, float, float] | None:
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (7, 7), 1.5)

    height, width = gray.shape
    if expected is None:
        x0, y0, x1, y1 = 0, 0, width, height
    else:
        cx, cy = expected
        x0 = max(0, int(cx - search_radius))
        y0 = max(0, int(cy - search_radius))
        x1 = min(width, int(cx + search_radius))
        y1 = min(height, int(cy + search_radius))

    roi = gray[y0:y1, x0:x1]
    if roi.size == 0:
        return None

    roi = cv2.equalizeHist(roi)
    min_radius = max(4, min(roi.shape[:2]) // 30)
    max_radius = max(min_radius + 4, min(roi.shape[:2]) // 3)
    circles = cv2.HoughCircles(
        roi,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(12, min_radius * 2),
        param1=80,
        param2=18,
        minRadius=min_radius,
        maxRadius=max_radius,
    )

    if circles is None:
        return None

    candidates = circles[0]
    if expected is None:
        chosen = max(candidates, key=lambda c: c[2])
    else:
        ex, ey = expected
        chosen = min(candidates, key=lambda c: (c[0] + x0 - ex) ** 2 + (c[1] + y0 - ey) ** 2)

    cx, cy, radius = float(chosen[0] + x0), float(chosen[1] + y0), float(chosen[2])
    score = float(radius)
    return cx, cy, radius, score
