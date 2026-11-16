from io import BytesIO

import pytest
from PIL import Image

from app.services.branding import DEFAULT_PALETTE, PALETTES, InvalidLogo, contrast_ratio, process_logo


def encode(image, fmt, **kwargs):
    out = BytesIO()
    image.save(out, format=fmt, **kwargs)
    return out.getvalue()


@pytest.mark.parametrize('name', sorted(PALETTES))
def test_palettes_have_readable_contrast(name):
    colors = PALETTES[name]
    assert set(colors) == {'primary', 'secondary', 'accent', 'background', 'surface', 'text'}
    assert all(len(v) == 7 and v.startswith('#') for v in colors.values())
    assert contrast_ratio(colors['text'], colors['background']) >= 4.5
    assert contrast_ratio(colors['text'], colors['surface']) >= 4.5
    assert contrast_ratio('#ffffff', colors['primary']) >= 4.5
    assert contrast_ratio('#ffffff', colors['secondary']) >= 4.5
    assert contrast_ratio(colors['primary'], colors['background']) >= 3


def test_default_palette_matches_existing_accent():
    assert PALETTES[DEFAULT_PALETTE]['primary'] == '#5934c9'


@pytest.mark.parametrize('fmt', ['PNG', 'JPEG', 'WEBP'])
def test_raster_logos_are_reencoded_as_bounded_png(fmt):
    image = Image.new('RGB', (1500, 500), (10, 20, 30))
    result = process_logo(encode(image, fmt))
    assert result.startswith(b'\x89PNG')
    assert Image.open(BytesIO(result)).size == (512, 171)


def test_metadata_is_stripped():
    image = Image.new('RGB', (10, 10))
    exif = Image.Exif(); exif[270] = 'secret'
    result = Image.open(BytesIO(process_logo(encode(image, 'JPEG', exif=exif.tobytes()))))
    assert not result.info and not result.getexif()


_NOISE = encode(Image.frombytes('RGB', (64, 64), bytes((i * 7919) % 251 for i in range(64 * 64 * 3))), 'PNG')
TRUNCATED = _NOISE[:len(_NOISE) // 2]


@pytest.mark.parametrize('data', [b'', b'<svg xmlns="http://www.w3.org/2000/svg"/>', b'GIF89a' + b'0' * 20, b'\x89PNG\r\n\x1a\ntruncated',
                                  TRUNCATED])
def test_invalid_or_non_raster_logos_are_rejected(data):
    with pytest.raises(InvalidLogo) as error:
        process_logo(data)
    assert error.value.status == 422


def test_gif_and_oversized_are_rejected():
    with pytest.raises(InvalidLogo):
        process_logo(encode(Image.new('RGB', (4, 4)), 'GIF'))
    with pytest.raises(InvalidLogo) as error:
        process_logo(b'0' * (1024 * 1024 + 1))
    assert error.value.status == 413
    with pytest.raises(InvalidLogo) as error:
        process_logo(encode(Image.new('1', (5000, 100)), 'PNG'))
    assert error.value.status == 413


def test_noisy_logo_that_exceeds_storage_budget_is_downscaled():
    import random
    from app.services.branding import MAX_LOGO_OUTPUT_BYTES
    noisy = Image.frombytes('RGB', (1024, 1024), random.Random(2).randbytes(1024 * 1024 * 3))
    upload = encode(noisy, 'JPEG', quality=30)
    assert len(upload) < 1024 * 1024
    plain = BytesIO()
    noisy.resize((512, 512)).convert('RGBA').save(plain, format='PNG', optimize=True)
    assert plain.tell() > MAX_LOGO_OUTPUT_BYTES  # a plain 512px re-encode would violate the column CHECK
    result = process_logo(upload)
    assert len(result) <= MAX_LOGO_OUTPUT_BYTES
    assert Image.open(BytesIO(result)).width <= 512
