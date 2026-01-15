# Roast - Turn Brutal Reviews into Engineering Tickets 🔥

AI-powered SaaS that turns brutal user feedback into actionable engineering tickets.

## 🏗️ Architecture

```
/backend   - Python 3.11 + FastAPI + ChromaDB + Sentence-Transformers
/frontend  - Next.js 14 + TypeScript + Tailwind CSS + Shadcn UI
```

## 🚀 Quick Start

### Backend Setup

```bash
cd backend
python -m venv venv
.\venv\Scripts\activate  # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend runs on `http://localhost:8000`

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:3000`

## 📋 Features

- **CSV Upload** - Drag & drop app reviews CSV
- **Noise Filtering** - Removes generic "good app" reviews
- **Deduplication** - ChromaDB clusters similar complaints
- **Metadata Extraction** - Auto-detects versions & devices
- **Severity Detection** - Classifies issues (critical/high/medium/low)
- **Cluster View** - Visualize grouped issues

## 🧪 Testing

```bash
# Test backend pipeline
python test_pipeline.py
```

## 🌐 Deployment

### Frontend (Vercel)

1. Connect your GitHub repo to Vercel
2. Set environment variable: `NEXT_PUBLIC_API_URL=<your-backend-url>`
3. Deploy

### Backend (Railway/Render)

1. Add `Procfile`:
   ```
   web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
2. Deploy to Railway or Render

## 📊 Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend Framework | FastAPI |
| Vector Store | ChromaDB |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 |
| Frontend | Next.js 14 (App Router) |
| UI Components | Shadcn UI + Tailwind CSS |
| State Management | TanStack Query |
| Data Validation | Pydantic V2 |

## 🔑 API Endpoints

- `GET /health` - Health check
- `POST /upload` - Upload CSV for processing
- `GET /clusters` - Get all roast clusters
- `GET /clusters/{id}` - Get specific cluster

## 📄 License

MIT
