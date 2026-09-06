import logging
from abc import ABC, abstractmethod
from typing import Optional
from app.core.multimodal.schemas import MAX_OCR_TEXT_BYTES, ProcessingError

logger = logging.getLogger(__name__)

class OCRUnavailableError(ProcessingError):
    pass

class OCRProvider(ABC):
    @abstractmethod
    def extract_text(self, file_path: str) -> str:
        pass

class TesseractOCRProvider(OCRProvider):
    def __init__(self):
        self._available = False
        try:
            import pytesseract
            from PIL import Image
            self._pytesseract = pytesseract
            self._Image = Image
            # Test if tesseract is installed by asking for version
            self._pytesseract.get_tesseract_version()
            self._available = True
        except ImportError:
            logger.warning("pytesseract or Pillow not installed. OCR will be unavailable.")
        except Exception as e:
            logger.warning(f"Tesseract binary not found or error initializing: {e}. OCR will be unavailable.")

    def extract_text(self, file_path: str) -> str:
        if not self._available:
            raise OCRUnavailableError("OCR is currently unavailable on this deployment.")

        try:
            image = self._Image.open(file_path)
            text = self._pytesseract.image_to_string(image)
            
            # Bound OCR output
            encoded = text.encode("utf-8")
            if len(encoded) > MAX_OCR_TEXT_BYTES:
                text = encoded[:MAX_OCR_TEXT_BYTES].decode("utf-8", "ignore")
                
            return text
        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            raise ProcessingError(f"OCR extraction failed: {str(e)}")
