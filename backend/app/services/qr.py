"""QR-code rendering (Phase 7).

Turns a shareable-report URL into a scannable PNG so a client can point their
phone at a screen in-studio and open their own report. Pure rendering — it
knows nothing about tokens or clients; the caller passes a finished URL.
"""
import base64
import io

import qrcode


def qr_png_bytes(url: str, box_size: int = 8, border: int = 2) -> bytes:
    """Render `url` as a PNG QR code and return the raw bytes."""
    qr = qrcode.QRCode(
        version=None,  # auto-size to fit the data
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def qr_png_base64(url: str, **kwargs) -> str:
    """Same as qr_png_bytes but base64-encoded (no data: prefix) for embedding
    in JSON / an <img src="data:image/png;base64,..."> tag."""
    return base64.b64encode(qr_png_bytes(url, **kwargs)).decode("ascii")
