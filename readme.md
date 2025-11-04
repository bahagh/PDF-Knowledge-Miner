# PDF Knowledge Miner - Semantic Search Engine

A semantic search engine for PDF documents built with FastAPI, PostgreSQL + pgvector, and Redis.

## 🚀 Key Features

### Core Functionality
- **Database Storage**: PostgreSQL with pgvector extension for vector similarity search
- **Caching**: Redis for embeddings and search results
- **PDF Processing**: Extract and chunk text from PDF documents
- **Text Chunking**: Split documents into searchable segments
- **Vector Embeddings**: Generate embeddings using sentence transformers

### API & Architecture
- **REST API**: FastAPI with async endpoints and automatic documentation
- **Containerization**: Docker and Docker Compose deployment
- **Configuration Management**: Environment-based settings
- **Health Checks**: Basic application monitoring

### Search Capabilities
- **Semantic Search**: Vector similarity search using sentence transformers
- **Question Answering**: Basic QA functionality with search results
- **Configurable Models**: Embedding model selection
- **Similarity Scoring**: Adjustable similarity thresholds

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   FastAPI App   │    │   PostgreSQL    │    │     Redis       │
│                 │────│   + pgvector    │    │   (Caching)     │
│  REST API       │    │                 │    │                 │
│  Health Check   │    │  Documents      │    │  Embeddings     │
│  Upload/Search  │    │  Chunks         │    │  Search Cache   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Core Services                               │
├─────────────────┬─────────────────┬─────────────────────────────┤
│ PDF Processor   │ Search Service  │ Cache Service               │
│ - PyMuPDF       │ - Vector Search │ - Redis Client              │
│ - Text Chunking │ - Basic QA      │ - TTL Management            │
└─────────────────┴─────────────────┴─────────────────────────────┘
```

## 📦 Installation

### Option 1: Docker (Recommended)

1. **Clone the repository**
   ```bash
   git clone https://github.com/bahagh/PDF-Knowledge-Miner.git
   cd PDF-Knowledge-Miner
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start services**
   ```bash
   # Start core services (app, database, cache)
   docker-compose up -d
   ```

4. **Verify deployment**
   ```bash
   curl http://localhost:8001/health
   ```

### Option 2: Local Development

1. **Prerequisites**
   - Python 3.11+
   - PostgreSQL 15+ with pgvector extension
   - Redis 7+
   - Poetry (recommended) or pip

2. **Install dependencies**
   ```bash
   # Using pip
   pip install -e .
   ```

3. **Setup databases**
   ```bash
   # PostgreSQL
   createdb pdf_miner
   psql pdf_miner -c "CREATE EXTENSION vector;"
   
   # Redis (start service)
   redis-server
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit database and Redis URLs in .env
   ```

5. **Initialize database**
   ```bash
   python -m app.cli init-database
   ```

6. **Start the application**
   ```bash
   # Start web server
   uvicorn app.main:app --reload --port 8001
   ```

## 🔧 Configuration

### Environment Variables

Key configuration options in `.env`:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/pdf_miner

# Redis
REDIS_URL=redis://localhost:6379/0

# Processing
PDF_DIR=data/pdfs
MAX_WORKERS=4
BATCH_SIZE=32

# ML Models
EMBEDDING_MODEL=all-MiniLM-L6-v2
QA_MODEL=deepset/roberta-base-squad2

# API
API_HOST=0.0.0.0
API_PORT=8001
```

### Performance Tuning

For optimal performance:

1. **Database**: Increase PostgreSQL `shared_buffers` and `effective_cache_size`
2. **Redis**: Configure memory limits and eviction policies
3. **Workers**: Adjust FastAPI worker count based on CPU cores

## 📖 Usage

### Web API

Access the interactive API documentation:
- **Swagger UI**: http://localhost:8001/docs
- **ReDoc**: http://localhost:8001/redoc

### Command Line Interface

Basic CLI commands available:

```bash
# Search documents  
python -m app.cli search -q "What is machine learning?" -k 5

# Initialize database
python -m app.cli init-database

# Check system status
python -m app.cli status
```

### API Endpoints

#### Document Management
- `POST /api/v1/documents/upload` - Upload PDF documents
- `GET /api/v1/documents/` - List documents with filtering
- `GET /api/v1/documents/{id}` - Get document details
- `DELETE /api/v1/documents/{id}` - Delete document
- `POST /api/v1/documents/{id}/reprocess` - Reprocess document

#### Search
- `POST /api/v1/search/` - Semantic search with optional QA
- `GET /api/v1/search/similar-documents/{id}` - Find similar documents
- `GET /api/v1/search/analytics` - Search analytics

#### Administration
- `POST /api/v1/admin/process-all` - Process all documents
- `POST /api/v1/admin/reprocess-failed` - Retry failed documents
- `POST /api/v1/admin/cache/clear` - Clear cache
- `GET /api/v1/admin/system/info` - System information

#### Health & Monitoring
- `GET /health` - Basic health check
- `GET /health/detailed` - Detailed health status
- `GET /health/stats` - System statistics

### Example Usage

```python
import httpx

# Upload a document
with open("document.pdf", "rb") as f:
    response = httpx.post(
        "http://localhost:8000/api/v1/documents/upload",
        files={"file": f}
    )

# Search with question answering
search_response = httpx.post(
    "http://localhost:8000/api/v1/search/",
    params={
        "query": "What are the main benefits of machine learning?",
        "top_k": 5,
        "include_qa": True
    }
)

results = search_response.json()
for result in results["results"]:
    print(f"Document: {result['document_filename']}")
    print(f"Answer: {result['qa_answer']}")
    print(f"Confidence: {result['qa_confidence']}")
```

## 🚀 Performance Improvements

### Compared to Original Version

| Metric | Original | Current | Improvement |
|--------|----------|---------|-------------|
| Processing Speed | ~15 min | ~2-3 min | **5-7x faster** |
| Memory Usage | High | Reduced | **Significant reduction** |
| Search Latency | 2-5s | 100-300ms | **10-20x faster** |
| Storage | File-based | Database | **Better scalability** |

### Key Optimizations

1. **Database Storage**: PostgreSQL with pgvector eliminates file I/O bottlenecks
2. **Caching Strategy**: Redis caches embeddings and search results
3. **Model Optimization**: Efficient loading and reuse of ML models
4. **Async Architecture**: Non-blocking I/O operations

## 🐳 Docker Deployment

### Basic Deployment

```bash
# Start all services
docker-compose up -d

# Monitor logs
docker-compose logs -f app

# Stop services
docker-compose down
```

### Development

```bash
# Start with logs
docker-compose up

# Access database
docker-compose exec postgres psql -U pdf_user -d pdf_miner

# View Redis data
docker-compose exec redis redis-cli
```

## 📊 Monitoring

### Health Checks

- **Application**: `/health` endpoint
- **Database**: Connection and query tests
- **Cache**: Redis ping and memory checks
- **Background Tasks**: Processing status monitoring

### Metrics (with Prometheus)

- Request rates and latency
- Database connection pools
- Cache hit rates
- Document processing metrics
- Error rates and exceptions

### Logging

Structured JSON logging with:
- Request/response tracking
- Performance metrics
- Error details with stack traces
- User activity tracking

## 🔒 Security

- **Environment Variables**: Configuration via .env files
- **Input Validation**: Pydantic models for API validation
- **File Upload Security**: File type and size validation
- **Database Security**: Parameterized queries and connection pooling

## 🧪 Testing

```bash
# Run the end-to-end test
python test_e2e.py

# Test API endpoints manually
curl -X POST "http://localhost:8001/api/v1/search/" \
     -H "Content-Type: application/json" \
     -d '{"query": "machine learning", "top_k": 5}'
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test your changes
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## 🙋‍♂️ Support

- **Documentation**: Check the `/docs` endpoint when running the application
- **Issues**: Create GitHub issues for bugs and feature requests

---

**Semantic PDF search made simple!** 🚀 This application provides efficient vector-based search capabilities for PDF document collections.
