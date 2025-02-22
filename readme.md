# Semantic PDF Search with FAISS and LLM Extraction

This project provides a semantic search engine for PDF documents using FAISS and a transformer-based QA model.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/bahagh/PDF-Knowledge-Miner.git
   cd sem
   ```
2. Install dependancies:

   ```bash
   pip install -r requirements.txt

   ```
3. You can Replace your PDF documents in data/pdfs/.
## Running the Project

To start the search (you"ll be asked to enter the prompt)
   ```bash
   python src/main.py


   ```

Or you can also provide the query via CLI :
   ```bash
   python src/main.py --query "What is nlp?"



   ```

## How It Works

- Extracts text from PDFs.
- Generates embeddings using all-MiniLM-L6-v2.
- Uses FAISS to index and search for relevant documents.
- Applies a QA model (deepset/roberta-base-squad2) to extract relevant answers.

## Automatic Index Updates
- If PDFs are modified or new PDFs are added, the index updates automatically.