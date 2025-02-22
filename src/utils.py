import os
import json
import logging
import PyPDF2
import numpy as np
import faiss
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

INDEX_DIR = os.path.join("data", "index")
INDEX_FILE = os.path.join(INDEX_DIR, "faiss_index.index")
METADATA_FILE = os.path.join(INDEX_DIR, "metadata.json")
PDF_DIR = os.path.join("data", "pdfs")

def extract_text_from_pdf(pdf_path):
    """Extracts text from a PDF file page by page."""
    texts = []
    try:
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                text = page.extract_text()
                if text:
                    texts.append(text.strip())
                else:
                    logging.warning(f"No text extracted from page {page_num+1} of {pdf_path}.")
    except Exception as e:
        logging.error(f"Error processing {pdf_path}: {e}")
    return texts

def get_pdf_metadata():
    """Returns a dictionary with PDF file names and their last modification timestamps."""
    pdf_files = [f for f in os.listdir(PDF_DIR) if f.lower().endswith(".pdf")]
    metadata = {file: os.path.getmtime(os.path.join(PDF_DIR, file)) for file in pdf_files}
    return metadata

def process_pdfs():
    """Processes all PDFs in the given directory and extracts text."""
    docs = []
    pdf_files = get_pdf_metadata()
    
    for filename in pdf_files:
        full_path = os.path.join(PDF_DIR, filename)
        page_texts = extract_text_from_pdf(full_path)
        if not page_texts:
            logging.warning(f"No text extracted from PDF: {filename}")
            continue
        for i, text in enumerate(page_texts):
            docs.append({
                "pdf": filename,
                "page": i + 1,
                "text": text
            })
    return docs

def save_index(index, metadata):
    """Saves the FAISS index and metadata mapping to disk."""
    os.makedirs(INDEX_DIR, exist_ok=True)
    faiss.write_index(index, INDEX_FILE)
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f)
    logging.info("Index and metadata saved successfully.")

def load_index():
    """Loads the FAISS index and metadata from disk if they exist."""
    if not os.path.exists(INDEX_FILE) or not os.path.exists(METADATA_FILE):
        return None, None
    
    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    current_metadata = get_pdf_metadata()
    if metadata != current_metadata:
        logging.info("PDFs have changed. Rebuilding index...")
        return None, None

    index = faiss.read_index(INDEX_FILE)
    logging.info("Index and metadata loaded from disk.")
    return index, metadata

def build_index(doc_texts, docs, model):
    """Creates embeddings from document texts, builds a FAISS index, and returns it."""
    embeddings = model.encode(doc_texts, show_progress_bar=True)
    embeddings_np = np.array(embeddings).astype("float32")
    
    dimension = embeddings_np.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings_np)

    # Save the index and metadata mapping
    save_index(index, get_pdf_metadata())
    return index
