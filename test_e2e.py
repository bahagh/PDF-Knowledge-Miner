#!/usr/bin/env python3
"""
End-to-end test for PDF Knowledge Miner API
Tests PDF upload and semantic search functionality
"""
import requests
import json
import os
import time
from pathlib import Path

# API configuration
BASE_URL = "http://localhost:8001"
API_PREFIX = "/api/v1"

def create_test_pdf():
    """Create a simple test PDF for testing"""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        import time
        
        # Create a unique filename with timestamp
        timestamp = int(time.time())
        filename = f"test_document_{timestamp}.pdf"
        c = canvas.Canvas(filename, pagesize=letter)
        
        # Add some content
        c.drawString(100, 750, "Test Document for PDF Knowledge Miner")
        c.drawString(100, 700, "This document contains information about artificial intelligence.")
        c.drawString(100, 650, "Machine learning is a subset of AI that focuses on algorithms.")
        c.drawString(100, 600, "Natural language processing helps computers understand human language.")
        c.drawString(100, 550, "Computer vision enables machines to interpret visual information.")
        c.drawString(100, 500, "Deep learning uses neural networks to solve complex problems.")
        
        c.save()
        print(f"✅ Created test PDF: {filename}")
        return filename
        
    except ImportError:
        print("❌ reportlab not available, creating a simple text file instead")
        # Create a simple text file as fallback
        import time
        timestamp = int(time.time())
        filename = f"test_document_{timestamp}.txt"
        with open(filename, 'w') as f:
            f.write("""Test Document for PDF Knowledge Miner

This document contains information about artificial intelligence.
Machine learning is a subset of AI that focuses on algorithms.
Natural language processing helps computers understand human language.
Computer vision enables machines to interpret visual information.
Deep learning uses neural networks to solve complex problems.
""")
        print(f"✅ Created test file: {filename}")
        return filename

def test_upload_document(filename):
    """Test document upload"""
    url = f"{BASE_URL}{API_PREFIX}/documents/upload"
    
    print(f"📤 Testing document upload...")
    print(f"   URL: {url}")
    
    try:
        with open(filename, 'rb') as f:
            files = {'file': (filename, f, 'application/pdf' if filename.endswith('.pdf') else 'text/plain')}
            data = {'title': 'Test Document', 'description': 'A test document for AI topics'}
            
            response = requests.post(url, files=files, data=data, timeout=30)
            
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"   Response: {json.dumps(result, indent=2)}")
            # Return True for successful upload, even without document_id
            return result.get('filename', True)
        else:
            print(f"   Error: {response.text}")
            return None
            
    except Exception as e:
        print(f"   ❌ Upload failed: {e}")
        return None

def test_search(query, doc_id=None):
    """Test semantic search"""
    url = f"{BASE_URL}{API_PREFIX}/search/"
    
    print(f"🔍 Testing search for: '{query}'")
    print(f"   URL: {url}")
    
    try:
        # Use POST request with query parameters
        params = {
            'query': query,
            'top_k': 3,
            'similarity_threshold': 0.5  # Lower threshold for more results
        }
        
        if doc_id:
            params['document_ids'] = [doc_id]
            
        response = requests.post(url, params=params, timeout=30)
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            results = result.get('results', [])
            print(f"   Found {len(results)} results")
            
            for i, res in enumerate(results, 1):
                print(f"   Result {i}:")
                print(f"     Score: {res.get('similarity_score', 'N/A'):.3f}")
                print(f"     Text: {res.get('text', '')[:100]}...")
                
            return result
        else:
            print(f"   Error: {response.text}")
            return None
            
    except Exception as e:
        print(f"   ❌ Search failed: {e}")
        return None

def test_list_documents():
    """Test document listing"""
    url = f"{BASE_URL}{API_PREFIX}/documents/"
    
    print(f"📋 Testing document listing...")
    print(f"   URL: {url}")
    
    try:
        response = requests.get(url, timeout=30)
        
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            docs = result.get('documents', [])
            print(f"   Found {len(docs)} documents")
            
            for doc in docs:
                print(f"   - {doc.get('title', 'Untitled')} (ID: {doc.get('id', 'N/A')})")
                
            return result
        else:
            print(f"   Error: {response.text}")
            return None
            
    except Exception as e:
        print(f"   ❌ Listing failed: {e}")
        return None

def main():
    """Run end-to-end tests"""
    print("🧪 PDF Knowledge Miner - End-to-End Test")
    print("=" * 50)
    
    # Check if API is running
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            print("❌ API is not running or not healthy")
            return
        print("✅ API is running and healthy")
    except:
        print("❌ Cannot connect to API")
        return
    
    print()
    
    # Create test document
    test_file = create_test_pdf()
    
    try:
        print()
        
        # Test document upload
        upload_result = test_upload_document(test_file)
        
        if upload_result:
            print(f"✅ Document uploaded successfully: {upload_result}")
            
            # Wait for document processing (background task)
            print("⏳ Waiting for document processing...")
            time.sleep(10)  # Increased wait time for processing
            
            print()
            
            # Test document listing
            test_list_documents()
            
            print()
            
            # Test various search queries (without specific document ID)
            search_queries = [
                "artificial intelligence",
                "machine learning algorithms", 
                "neural networks",
                "computer vision",
                "natural language processing"
            ]
            
            for query in search_queries:
                test_search(query)  # Remove doc_id parameter
                print()
                
        else:
            print("❌ Document upload failed, skipping search tests")
            
    finally:
        # Cleanup
        if os.path.exists(test_file):
            os.remove(test_file)
            print(f"🧹 Cleaned up test file: {test_file}")

if __name__ == "__main__":
    main()