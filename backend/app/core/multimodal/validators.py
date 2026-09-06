import struct
from typing import Tuple, Optional
from app.core.multimodal.schemas import (
    MediaValidationError,
    MAX_IMAGE_BYTES,
    MAX_PIXELS
)

def validate_image(content: bytes) -> Tuple[str, Optional[int], Optional[int]]:
    """
    Validates image bounds (bytes, pixels) and parses signature.
    Returns (media_type, width, height) or raises MediaValidationError.
    """
    if len(content) > MAX_IMAGE_BYTES:
        raise MediaValidationError(f"File too large: {len(content)} bytes exceeds max {MAX_IMAGE_BYTES} bytes")
    
    if len(content) < 16:
        raise MediaValidationError("File too small to be a valid image")

    # PNG
    if content.startswith(b'\x89PNG\r\n\x1a\n'):
        if len(content) >= 24:
            width, height = struct.unpack(">II", content[16:24])
            _check_pixels(width, height)
            return ("image/png", width, height)
        raise MediaValidationError("Truncated PNG header")

    # JPEG
    if content.startswith(b'\xff\xd8'):
        width, height = _parse_jpeg_dimensions(content)
        if width and height:
            _check_pixels(width, height)
        return ("image/jpeg", width, height)

    # WEBP
    if content.startswith(b'RIFF') and content[8:12] == b'WEBP':
        width, height = _parse_webp_dimensions(content)
        if width and height:
            _check_pixels(width, height)
        return ("image/webp", width, height)

    raise MediaValidationError("Unsupported or invalid image signature")

def _check_pixels(width: int, height: int):
    if width * height > MAX_PIXELS:
        raise MediaValidationError(f"Image too large: {width}x{height} exceeds max {MAX_PIXELS} pixels")

def _parse_jpeg_dimensions(data: bytes) -> Tuple[Optional[int], Optional[int]]:
    offset = 2
    length = len(data)
    while offset < length:
        while offset < length and data[offset] != 0xFF:
            offset += 1
        while offset < length and data[offset] == 0xFF:
            offset += 1
        
        if offset >= length:
            break
            
        marker = data[offset]
        offset += 1
        
        if marker in [0xD8, 0xD9, 0x01] or (0xD0 <= marker <= 0xD7):
            continue
            
        if offset + 2 > length:
            break
            
        chunk_length = struct.unpack(">H", data[offset:offset+2])[0]
        
        # 0xC0 to 0xC3, 0xC5 to 0xC7, 0xC9 to 0xCB, 0xCD to 0xCF are SOF markers
        if marker in [0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF]:
            if offset + 7 <= length:
                height, width = struct.unpack(">HH", data[offset+3:offset+7])
                return width, height
                
        offset += chunk_length
    return None, None

def _parse_webp_dimensions(data: bytes) -> Tuple[Optional[int], Optional[int]]:
    if len(data) < 30:
        return None, None
        
    chunk_header = data[12:16]
    if chunk_header == b'VP8 ':
        width, height = struct.unpack("<HH", data[26:30])
        return width & 0x3fff, height & 0x3fff
    elif chunk_header == b'VP8L':
        b1, b2, b3, b4 = struct.unpack("BBBB", data[21:25])
        width = 1 + (((b2 & 0x3F) << 8) | b1)
        height = 1 + (((b4 & 0x0F) << 10) | (b3 << 2) | ((b2 & 0xC0) >> 6))
        return width, height
    elif chunk_header == b'VP8X':
        # VP8X chunk has width/height in bytes 24..29 (24-bit ints)
        width = 1 + int.from_bytes(data[24:27], 'little')
        height = 1 + int.from_bytes(data[27:30], 'little')
        return width, height
    return None, None
