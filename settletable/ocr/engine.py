"""Local OCR Engine interface and safe image header decoding."""
import os
from pathlib import Path
import struct
from typing import Protocol

from .models import OcrLine

MAX_IMAGE_BYTES = 5_242_880  # 5 MB
MAX_IMAGE_WIDTH = 4096
MAX_IMAGE_HEIGHT = 4096
MAX_IMAGE_PIXELS = 16_777_216  # 16 MP


class OcrError(Exception):
    """Base error for OCR operations."""


class OcrUnavailableError(OcrError):
    """Raised when the local OCR engine is not installed or unavailable."""


class InvalidImageError(OcrError):
    """Raised when image bytes are malformed, unsupported, or exceed safe bounds."""


def parse_image_dimensions(data: bytes, fmt: str) -> tuple[int, int]:
    """Parse image (width, height) directly from header without allocating raster bitmap."""
    if fmt == 'png':
        if len(data) < 24:
            raise InvalidImageError('truncated_image_header')
        width, height = struct.unpack('>II', data[16:24])
        return width, height

    if fmt == 'jpeg':
        # Parse JPEG markers to find Start Of Frame (SOF0 - SOF3)
        idx = 2
        data_len = len(data)
        while idx < data_len:
            if data[idx] != 0xFF:
                idx += 1
                continue
            marker = data[idx + 1] if idx + 1 < data_len else 0
            # SOF0 (0xC0) to SOF3 (0xC3), SOF5-SOF7, SOF9-SOF11, SOF13-SOF15
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                if idx + 9 <= data_len:
                    height, width = struct.unpack('>HH', data[idx + 5:idx + 9])
                    return width, height
                raise InvalidImageError('truncated_image_header')
            if marker in (0xD9, 0xDA):  # EOI or SOS (start of scan)
                break
            if idx + 4 <= data_len:
                length = struct.unpack('>H', data[idx + 2:idx + 4])[0]
                idx += 2 + length
            else:
                break
        raise InvalidImageError('missing_sof_in_jpeg')

    if fmt == 'webp':
        if len(data) < 30:
            raise InvalidImageError('truncated_image_header')
        chunk = data[12:16]
        if chunk == b'VP8 ':
            # Lossy WebP: frame tag at 20, keyframe code at 23-26, dims at 26
            if len(data) >= 30 and data[23:26] == b'\x9d\x01\x2a':
                w, h = struct.unpack('<HH', data[26:30])
                return w & 0x3FFF, h & 0x3FFF
        elif chunk == b'VP8L':
            # Lossless WebP: 1 byte signature 0x2f, 14 bits width-1, 14 bits height-1
            if len(data) >= 25 and data[20] == 0x2F:
                b1, b2, b3, b4 = data[21:25]
                width = 1 + (((b2 & 0x3F) << 8) | b1)
                height = 1 + (((b4 & 0x0F) << 10) | (b3 << 2) | ((b2 & 0xC0) >> 6))
                return width, height
        elif chunk == b'VP8X':
            # Extended WebP: 24-bit LE canvas width-1 and height-1 at offset 24
            if len(data) >= 30:
                width = 1 + struct.unpack('<I', data[24:27] + b'\x00')[0]
                height = 1 + struct.unpack('<I', data[27:30] + b'\x00')[0]
                return width, height
        raise InvalidImageError('unsupported_webp_format')

    raise InvalidImageError('unsupported_format')


def validate_image_payload(data: bytes, expected_mime: str | None = None) -> tuple[str, int, int]:
    """Validate binary image data for magic bytes, declared MIME type, and safe dimension bounds.
    
    Returns (detected_format, width, height).
    """
    if not data:
        raise InvalidImageError('empty_payload')
    if len(data) > MAX_IMAGE_BYTES:
        raise InvalidImageError('payload_too_large')

    detected_fmt: str | None = None
    if len(data) >= 8 and data[:8] == b'\x89PNG\r\n\x1a\n':
        detected_fmt = 'png'
    elif len(data) >= 3 and data[:3] == b'\xff\xd8\xff':
        detected_fmt = 'jpeg'
    elif len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        detected_fmt = 'webp'

    if not detected_fmt:
        raise InvalidImageError('invalid_magic_bytes')

    if expected_mime:
        expected_mime = expected_mime.split(';')[0].strip().lower()
        mime_map = {
            'image/png': 'png',
            'image/jpeg': 'jpeg',
            'image/jpg': 'jpeg',
            'image/webp': 'webp',
        }
        mapped = mime_map.get(expected_mime)
        if mapped and mapped != detected_fmt:
            raise InvalidImageError('content_type_mismatch')

    try:
        width, height = parse_image_dimensions(data, detected_fmt)
    except InvalidImageError:
        raise
    except Exception as exc:
        raise InvalidImageError('malformed_image_header') from exc

    if width <= 0 or height <= 0:
        raise InvalidImageError('invalid_dimensions')
    if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT or (width * height) > MAX_IMAGE_PIXELS:
        raise InvalidImageError('image_dimensions_too_large')

    return detected_fmt, width, height


class OcrEngine(Protocol):
    """Protocol for local OCR engine implementations."""

    def recognize(self, image_bytes: bytes) -> list[OcrLine]:
        """Recognize lines of text and their spatial coordinates in the image."""
        ...


class MockOcrEngine:
    """Deterministic OCR engine for testing without native ML dependencies.
    
    Replays pre-configured OcrLine lists or mapped token fixtures.
    """

    def __init__(self, default_lines: list[OcrLine] | None = None, fixtures: dict[str, list[OcrLine]] | None = None):
        self._default_lines = default_lines or []
        self._fixtures = fixtures or {}

    def recognize(self, image_bytes: bytes) -> list[OcrLine]:
        validate_image_payload(image_bytes)
        import hashlib
        h = hashlib.sha256(image_bytes).hexdigest()
        if h in self._fixtures:
            return self._fixtures[h]
        return list(self._default_lines)


class RapidOcrEngine:
    """Local CPU OCR engine wrapping RapidOCR with ONNX Runtime."""

    def __init__(self, num_threads: int = 4):
        try:
            try:
                from rapidocr import RapidOCR
                self._engine = RapidOCR(params={
                    "EngineConfig.onnxruntime.intra_op_num_threads": num_threads,
                    "EngineConfig.onnxruntime.inter_op_num_threads": 1,
                })
            except ImportError:
                from rapidocr_onnxruntime import RapidOCR
                self._engine = RapidOCR()
        except ImportError as err:
            raise OcrUnavailableError("rapidocr / rapidocr_onnxruntime is not installed on this system") from err
        except Exception as err:
            raise OcrUnavailableError(f"Failed to initialize RapidOCR engine: {err}") from err

    def recognize(self, image_bytes: bytes) -> list[OcrLine]:
        validate_image_payload(image_bytes)
        try:
            result = self._engine(image_bytes)
            if hasattr(result, "txts") and hasattr(result, "scores") and hasattr(result, "boxes"):
                texts = result.txts or []
                scores = result.scores or []
                boxes = result.boxes if result.boxes is not None else []
            elif isinstance(result, tuple) and len(result) >= 1:
                raw_list = result[0] or []
                boxes = [item[0] for item in raw_list]
                texts = [item[1] for item in raw_list]
                scores = [item[2] for item in raw_list]
            elif isinstance(result, list):
                boxes = [item[0] for item in result]
                texts = [item[1] for item in result]
                scores = [item[2] for item in result]
            else:
                texts, scores, boxes = [], [], []

            lines = []
            for txt, score, box in zip(texts, scores, boxes):
                pts = tuple(tuple(int(coord) for coord in pt) for pt in box)
                lines.append(OcrLine(text=str(txt), score=float(score), box=pts))
            return lines
        except Exception as err:
            raise OcrError(f"RapidOCR recognition failed: {err}") from err
