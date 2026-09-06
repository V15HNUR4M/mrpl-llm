from typing import List
import uuid

from app.core.rag.schemas import ParsedDocument, DocumentChunk

class TextChunker:
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, parsed_doc: ParsedDocument, document_id: str, document_version_id: str) -> List[DocumentChunk]:
        """
        Splits a ParsedDocument into deterministic DocumentChunks.
        In a production system this would use LangChain's RecursiveCharacterTextSplitter 
        or similar to respect paragraphs/sentences. We implement a simplified token/character splitter.
        """
        text = parsed_doc.content
        chunks = []
        
        if not text:
            return []

        # Simple character-based chunking with overlap for this implementation
        # A more advanced chunker would split on \n\n, \n, " ", "" hierarchically.
        start = 0
        chunk_index = 0
        text_length = len(text)

        while start < text_length:
            end = min(start + self.chunk_size, text_length)
            
            # If we're not at the end of the text, try to find a natural break (like a newline or space)
            # to avoid cutting in the middle of a word.
            if end < text_length:
                # Look backwards for a newline or space
                break_point = text.rfind('\n', start, end)
                if break_point == -1 or break_point <= start:
                    break_point = text.rfind(' ', start, end)
                
                if break_point != -1 and break_point > start:
                    end = break_point + 1 # Include the space/newline

            chunk_text = text[start:end].strip()
            if chunk_text: # Avoid empty chunks
                # Deterministic chunk ID based on document_version_id and chunk_index
                chunk_id = f"{document_version_id}-chunk-{chunk_index}"
                
                # Try to extract page number if it's there (specifically for our PDF parser implementation)
                page_number = None
                if chunk_text.startswith("--- Page ") and "---" in chunk_text[9:]:
                    try:
                        page_str = chunk_text.split("---")[1].replace("Page", "").strip()
                        page_number = int(page_str)
                    except (ValueError, IndexError):
                        pass

                chunk = DocumentChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    document_version_id=document_version_id,
                    content=chunk_text,
                    chunk_index=chunk_index,
                    page_number=page_number,
                    section=None,
                    metadata=parsed_doc.metadata.copy()
                )
                chunks.append(chunk)
                chunk_index += 1
            
            # Advance start by chunk_size - overlap, but ensure we always move forward
            step = end - start - self.chunk_overlap
            if step <= 0:
                step = 1 # Prevent infinite loop if overlap is larger than chunk size
                
            start += step

        return chunks
