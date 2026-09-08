"""Límites de tamaño al leer uploads (Excel de flujo, etc.)."""

MAX_FLUJO_EXCEL_BYTES = 4 * 1024 * 1024
_READ_CHUNK = 64 * 1024


class UploadTooLarge(Exception):
    pass


async def read_upload_limited(file, max_bytes: int = MAX_FLUJO_EXCEL_BYTES) -> bytes:
    buf = bytearray()
    while True:
        chunk = await file.read(_READ_CHUNK)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise UploadTooLarge()
    return bytes(buf)
