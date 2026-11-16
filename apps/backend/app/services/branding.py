"""Predefined tenant palettes and safe logo processing; no arbitrary CSS or colours."""
import hashlib
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_LOGO_UPLOAD_BYTES = 1024 * 1024
MAX_LOGO_SOURCE_SIDE = 4096
MAX_LOGO_SOURCE_PIXELS = 12_000_000
LOGO_BOUND = 512
MAX_LOGO_OUTPUT_BYTES = 500_000  # below the 512 KiB column CHECK
_ALLOWED_FORMATS = {'PNG', 'JPEG', 'WEBP'}

# Tokens: primary (buttons/accents, white text on it), secondary, accent,
# background, surface and text. Contrast is verified in the test suite (WCAG AA).
PALETTES: dict[str, dict[str, str]] = {
    'violet': {'primary': '#5934c9', 'secondary': '#3b2a73', 'accent': '#7c4dff', 'background': '#faf9ff', 'surface': '#ffffff', 'text': '#231a39'},
    'ocean': {'primary': '#0b5fa5', 'secondary': '#083b66', 'accent': '#1f8fd6', 'background': '#f4f9fd', 'surface': '#ffffff', 'text': '#10243a'},
    'forest': {'primary': '#1d6b43', 'secondary': '#134a2e', 'accent': '#2e9e63', 'background': '#f5faf6', 'surface': '#ffffff', 'text': '#14281d'},
    'sunset': {'primary': '#b4421a', 'secondary': '#7a2a0e', 'accent': '#e0662f', 'background': '#fff8f4', 'surface': '#ffffff', 'text': '#33190e'},
    'graphite': {'primary': '#374151', 'secondary': '#1f2937', 'accent': '#6b7280', 'background': '#f7f8f9', 'surface': '#ffffff', 'text': '#111827'},
}
DEFAULT_PALETTE = 'violet'


def contrast_ratio(foreground: str, background: str) -> float:
    def luminance(color: str) -> float:
        channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


class InvalidLogo(ValueError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def process_logo(data: bytes) -> bytes:
    """Decode the pixels, bound the size and return a metadata-free PNG."""
    if not data:
        raise InvalidLogo(422, 'Invalid image')
    if len(data) > MAX_LOGO_UPLOAD_BYTES:
        raise InvalidLogo(413, 'Logo too large')
    try:
        with Image.open(BytesIO(data), formats=sorted(_ALLOWED_FORMATS)) as probe:
            probe.verify()  # structural check; other modules may enable LOAD_TRUNCATED_IMAGES globally
        with Image.open(BytesIO(data), formats=sorted(_ALLOWED_FORMATS)) as image:
            if image.width > MAX_LOGO_SOURCE_SIDE or image.height > MAX_LOGO_SOURCE_SIDE or image.width * image.height > MAX_LOGO_SOURCE_PIXELS:
                raise InvalidLogo(413, 'Logo dimensions too large')
            image.seek(0)
            image.load()
            image = ImageOps.exif_transpose(image).convert('RGBA')
    except InvalidLogo:
        raise
    except (UnidentifiedImageError, OSError, ValueError, EOFError, Image.DecompressionBombError, SyntaxError):
        raise InvalidLogo(422, 'Invalid image')
    return _fit(image)


def _fit(image: Image.Image) -> bytes:
    """Re-encode as a metadata-free PNG within the stored-size budget.

    Tries the full bound, then a 256-colour quantized copy (keeps the size), then a
    256px downscale; 256x256 RGBA is at most ~262 kB so the last step always fits and
    the final check is purely defensive.
    """
    image.thumbnail((LOGO_BOUND, LOGO_BOUND))
    small = image.copy()
    small.thumbnail((256, 256))
    for candidate in (image, image.quantize(colors=256, method=Image.Quantize.FASTOCTREE), small):
        # Fresh image (or a quantized copy of one): no metadata survives.
        clean = candidate if candidate.mode == 'P' else Image.frombytes(candidate.mode, candidate.size, candidate.tobytes())
        output = BytesIO()
        clean.save(output, format='PNG', optimize=True)
        if output.tell() <= MAX_LOGO_OUTPUT_BYTES:
            return output.getvalue()
    raise InvalidLogo(422, 'Logo too complex; use a simpler image')


def logo_token(tenant_id, theme_version: int) -> str:
    """Opaque tenant+version token used in the public logo path."""
    return hashlib.sha256(f'{tenant_id}:{theme_version}'.encode()).hexdigest()[:32]
