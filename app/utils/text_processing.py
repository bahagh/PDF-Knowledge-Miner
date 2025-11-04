"""
Text processing utilities for intelligent chunking and preprocessing.
"""
import re
from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class TextChunk:
    """Represents a text chunk with metadata"""
    text: str
    page_number: int
    chunk_index: int
    start_char: int
    end_char: int
    token_count: int


class TextChunker:
    """Intelligent text chunking with overlap and semantic boundaries"""
    
    def __init__(self, max_chunk_size: int = 512, chunk_overlap: int = 50):
        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = chunk_overlap
        
        # Patterns for sentence and paragraph boundaries
        self.sentence_pattern = re.compile(r'[.!?]+\s+')
        self.paragraph_pattern = re.compile(r'\n\s*\n')
        self.whitespace_pattern = re.compile(r'\s+')
    
    def clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        # Remove excessive whitespace
        text = self.whitespace_pattern.sub(' ', text)
        
        # Remove common PDF artifacts
        text = re.sub(r'\f', '\n', text)  # Form feed to newline
        text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', text)  # Control characters
        
        # Normalize quotes (escape Unicode quotes properly)
        text = re.sub(r'[""„‚]', '"', text)  # Various double quotes to standard double quote
        text = re.sub(r'[''‚]', "'", text)   # Various single quotes to standard single quote
        
        # Fix common spacing issues
        text = re.sub(r'\s+([.,:;!?])', r'\1', text)  # Remove space before punctuation
        text = re.sub(r'([.!?])\s*([A-Z])', r'\1 \2', text)  # Ensure space after sentence end
        
        return text.strip()
    
    def estimate_token_count(self, text: str) -> int:
        """Estimate token count (rough approximation)"""
        # Simple heuristic: average 4 characters per token
        return len(text) // 4
    
    def split_by_sentences(self, text: str) -> List[str]:
        """Split text into sentences"""
        sentences = self.sentence_pattern.split(text)
        # Remove empty sentences and strip whitespace
        return [s.strip() for s in sentences if s.strip()]
    
    def split_by_paragraphs(self, text: str) -> List[str]:
        """Split text into paragraphs"""
        paragraphs = self.paragraph_pattern.split(text)
        return [p.strip() for p in paragraphs if p.strip()]
    
    def chunk_text(self, text: str, page_number: int = 1) -> List[Dict[str, Any]]:
        """
        Chunk text intelligently with overlap and semantic boundaries.
        
        Args:
            text: Input text to chunk
            page_number: Page number for metadata
            
        Returns:
            List of chunk dictionaries with metadata
        """
        # Clean the text
        cleaned_text = self.clean_text(text)
        
        if not cleaned_text:
            return []
        
        # If text is short enough, return as single chunk
        if self.estimate_token_count(cleaned_text) <= self.max_chunk_size:
            return [{
                "text": cleaned_text,
                "page_number": page_number,
                "chunk_index": 0,
                "start_char": 0,
                "end_char": len(cleaned_text),
                "token_count": self.estimate_token_count(cleaned_text)
            }]
        
        chunks = []
        chunk_index = 0
        
        # Try to split by paragraphs first
        paragraphs = self.split_by_paragraphs(cleaned_text)
        
        current_chunk = ""
        current_start = 0
        
        for paragraph in paragraphs:
            paragraph_tokens = self.estimate_token_count(paragraph)
            current_tokens = self.estimate_token_count(current_chunk)
            
            # If adding this paragraph would exceed max size
            if current_tokens + paragraph_tokens > self.max_chunk_size and current_chunk:
                # Save current chunk
                chunks.append({
                    "text": current_chunk.strip(),
                    "page_number": page_number,
                    "chunk_index": chunk_index,
                    "start_char": current_start,
                    "end_char": current_start + len(current_chunk),
                    "token_count": current_tokens
                })
                chunk_index += 1
                
                # Start new chunk with overlap
                if self.chunk_overlap > 0 and current_chunk:
                    overlap_text = self._get_overlap_text(current_chunk, self.chunk_overlap)
                    current_chunk = overlap_text + " " + paragraph
                    current_start = current_start + len(current_chunk) - len(overlap_text) - len(paragraph) - 1
                else:
                    current_chunk = paragraph
                    current_start = current_start + len(current_chunk)
            
            # If paragraph itself is too large, split by sentences
            elif paragraph_tokens > self.max_chunk_size:
                # Save current chunk if not empty
                if current_chunk:
                    chunks.append({
                        "text": current_chunk.strip(),
                        "page_number": page_number,
                        "chunk_index": chunk_index,
                        "start_char": current_start,
                        "end_char": current_start + len(current_chunk),
                        "token_count": current_tokens
                    })
                    chunk_index += 1
                
                # Split paragraph by sentences
                sentence_chunks = self._chunk_by_sentences(paragraph, page_number, chunk_index)
                chunks.extend(sentence_chunks)
                chunk_index += len(sentence_chunks)
                
                current_chunk = ""
                current_start = current_start + len(paragraph)
            
            else:
                # Add paragraph to current chunk
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph
        
        # Add final chunk if not empty
        if current_chunk:
            chunks.append({
                "text": current_chunk.strip(),
                "page_number": page_number,
                "chunk_index": chunk_index,
                "start_char": current_start,
                "end_char": current_start + len(current_chunk),
                "token_count": self.estimate_token_count(current_chunk)
            })
        
        return chunks
    
    def _chunk_by_sentences(self, text: str, page_number: int, start_chunk_index: int) -> List[Dict[str, Any]]:
        """Chunk text by sentences when paragraphs are too large"""
        sentences = self.split_by_sentences(text)
        chunks = []
        chunk_index = start_chunk_index
        
        current_chunk = ""
        current_start = 0
        
        for sentence in sentences:
            sentence_tokens = self.estimate_token_count(sentence)
            current_tokens = self.estimate_token_count(current_chunk)
            
            if current_tokens + sentence_tokens > self.max_chunk_size and current_chunk:
                # Save current chunk
                chunks.append({
                    "text": current_chunk.strip(),
                    "page_number": page_number,
                    "chunk_index": chunk_index,
                    "start_char": current_start,
                    "end_char": current_start + len(current_chunk),
                    "token_count": current_tokens
                })
                chunk_index += 1
                
                # Start new chunk with overlap
                if self.chunk_overlap > 0:
                    overlap_text = self._get_overlap_text(current_chunk, self.chunk_overlap)
                    current_chunk = overlap_text + " " + sentence
                else:
                    current_chunk = sentence
                
                current_start = current_start + len(current_chunk)
            else:
                if current_chunk:
                    current_chunk += " " + sentence
                else:
                    current_chunk = sentence
        
        # Add final chunk
        if current_chunk:
            chunks.append({
                "text": current_chunk.strip(),
                "page_number": page_number,
                "chunk_index": chunk_index,
                "start_char": current_start,
                "end_char": current_start + len(current_chunk),
                "token_count": self.estimate_token_count(current_chunk)
            })
        
        return chunks
    
    def _get_overlap_text(self, text: str, overlap_size: int) -> str:
        """Get overlap text from the end of a chunk"""
        words = text.split()
        if len(words) <= overlap_size:
            return text
        
        overlap_words = words[-overlap_size:]
        return " ".join(overlap_words)


class TextPreprocessor:
    """Text preprocessing utilities"""
    
    @staticmethod
    def remove_headers_footers(text: str, page_number: int) -> str:
        """Remove common headers and footers patterns"""
        lines = text.split('\n')
        
        # Remove very short lines at the beginning and end (likely headers/footers)
        filtered_lines = []
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Skip very short lines at the top or bottom of the page
            if len(line) < 10 and (i < 3 or i > len(lines) - 4):
                continue
            
            # Skip lines that are just page numbers
            if re.match(r'^\d+$', line) and len(line) < 5:
                continue
            
            # Skip common header/footer patterns
            if re.match(r'^(chapter|section|\d+\.\d+)', line.lower()):
                continue
            
            filtered_lines.append(line)
        
        return '\n'.join(filtered_lines)
    
    @staticmethod
    def extract_metadata_from_text(text: str) -> Dict[str, Any]:
        """Extract metadata like headings, lists, etc. from text"""
        metadata = {
            "has_headings": bool(re.search(r'^[A-Z][A-Z\s]+$', text, re.MULTILINE)),
            "has_lists": bool(re.search(r'^\s*[-•*]\s+', text, re.MULTILINE)),
            "has_numbered_lists": bool(re.search(r'^\s*\d+\.\s+', text, re.MULTILINE)),
            "has_tables": bool(re.search(r'\|\s*[^|]+\s*\|', text)),
            "line_count": len(text.split('\n')),
            "word_count": len(text.split()),
            "char_count": len(text),
        }
        
        return metadata