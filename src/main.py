import os
import sys
import argparse
import logging
import numpy as np
from sentence_transformers import SentenceTransformer
from transformers import pipeline
from utils import process_pdfs, load_index, build_index

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def main(args):
    pdf_dir = os.path.join("data", "pdfs")

    # Load embedding model
    logging.info("Loading the SentenceTransformer model...")
    model = SentenceTransformer('all-MiniLM-L6-v2')

    # Check for an existing index
    index, docs = load_index()

    if index is None or docs is None:
        logging.info("Processing PDFs and building a new index...")
        docs = process_pdfs()
        if not docs:
            logging.error("No documents found. Please ensure there are PDFs in the directory.")
            sys.exit(1)
        doc_texts = [doc["text"] for doc in docs]
        index = build_index(doc_texts, docs, model)

    # Load QA pipeline
    logging.info("Loading the Question Answering pipeline...")
    qa_pipeline = pipeline("question-answering", model="deepset/roberta-base-squad2")

    # Process query
    query = args.query if args.query else input("Enter your query (or 'exit' to quit): ").strip()
    
    while query.lower() not in ["exit", "quit"]:
        query_embedding = model.encode([query])
        query_embedding_np = np.array(query_embedding).astype("float32")

        # Search index
        k = 1
        distances, indices = index.search(query_embedding_np, k)
        best_idx = indices[0][0]
        best_doc = docs[best_idx]

        print(f"\nMatch found: {best_doc['pdf']} | Page: {best_doc['page']}")
        print("\nRetrieved Document Excerpt:")
        print(best_doc["text"])

        try:
            qa_result = qa_pipeline(question=query, context=best_doc["text"])
            answer = qa_result.get("answer", "No answer extracted.")
        except Exception as e:
            logging.error(f"Error during QA extraction: {e}")
            answer = "Error extracting answer."

        print("\nExtracted Relevant Information:")
        print(answer)

        query = input("\nEnter a new query (or 'exit' to quit): ").strip()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Semantic PDF Search with FAISS and LLM-based extraction."
    )
    parser.add_argument("--query", type=str, default=None, help="Initial query (otherwise interactive input).")
    args = parser.parse_args()
    main(args)
