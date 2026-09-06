import pytest
from app.core.rag.parser import ParserRegistry, TXTParser, MarkdownParser, PDFParser
from app.core.rag.errors import UnsupportedFormatError, ParsingError
import io

def test_parser_registry():
    registry = ParserRegistry()
    assert isinstance(registry.get_parser("text/plain", "txt"), TXTParser)
    assert isinstance(registry.get_parser("text/markdown", "md"), MarkdownParser)
    assert isinstance(registry.get_parser("application/pdf", "pdf"), PDFParser)
    
    with pytest.raises(UnsupportedFormatError):
        registry.get_parser("image/jpeg", "jpg")

def test_txt_parser():
    parser = TXTParser()
    content = b"Hello world"
    doc = parser.parse(content, {"test": 123})
    assert doc.content == "Hello world"
    assert doc.metadata == {"test": 123}

def test_md_parser():
    parser = MarkdownParser()
    content = b"# Heading\nContent"
    doc = parser.parse(content)
    assert doc.content == "# Heading\nContent"
