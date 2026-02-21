# 🔥 ROAST - How to Run the Project

## ✅ Cleaned Up:
- ✓ Removed test databases (test_chroma_db/)
- ✓ Removed test CSV files
- ✓ Removed old SQL migration scripts
- ✓ Removed build artifacts
- ✓ Project is ready to run!

---

## 🚀 How to Execute

### **Step 1: Backend Setup**

```powershell
# Navigate to backend
cd backend

# Create virtual environment (if not exists)
python -m venv venv

# Activate virtual environment
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file (if not exists)
# Add these variables:
# PROVIDER_3_API_KEY=your_deepseek_key
# PROVIDER_5_API_KEY=your_together_ai_key

# Start the backend server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Backend will run on:** `http://localhost:8000`

**Test it:** Open `http://localhost:8000/health` in browser

---

### **Step 2: Frontend Setup** (In a NEW terminal)

```powershell
# Navigate to frontend
cd frontend

# Install dependencies (if node_modules missing)
npm install

# Create .env.local file (if not exists)
# Add these variables:
# NEXT_PUBLIC_SUPABASE_URL=your_supabase_url
# NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
# SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

# Start the frontend dev server
npm run dev
```

**Frontend will run on:** `http://localhost:3000`

---

## 📝 Quick Commands

### Backend Only:
```powershell
cd backend
.\venv\Scripts\activate
uvicorn app.main:app --reload
```

### Frontend Only:
```powershell
cd frontend
npm run dev
```

### Both Together:
**Terminal 1 (Backend):**
```powershell
cd backend; .\venv\Scripts\activate; uvicorn app.main:app --reload
```

**Terminal 2 (Frontend):**
```powershell
cd frontend; npm run dev
```

---

## 🔑 Required Environment Variables

### Backend (.env):
```env
PROVIDER_3_API_KEY=sk-xxx    # DeepSeek API key
PROVIDER_5_API_KEY=sk-yyy    # Together AI API key
```

### Frontend (.env.local):
```env
NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJxxx...
SUPABASE_SERVICE_ROLE_KEY=eyJxxx...
```

---

## 🧪 Test the System

1. **Backend Health Check:**
   - Open: `http://localhost:8000/health`
   - Should see: `{"status":"Roast is cooking"}`

2. **Frontend Login:**
   - Open: `http://localhost:3000`
   - Click "Sign in with Google"
   - Should redirect to dashboard

3. **Upload CSV:**
   - Go to: `http://localhost:3000/upload`
   - Upload `chatgpt_reviews.csv`
   - Backend processes → frontend shows tickets

---

## 🐛 Troubleshooting

**Backend won't start?**
```powershell
# Check if port 8000 is in use
netstat -ano | findstr :8000

# Kill the process if needed
taskkill /PID <process_id> /F
```

**Frontend won't start?**
```powershell
# Check if port 3000 is in use
netstat -ano | findstr :3000

# Clear npm cache
npm cache clean --force
rm -r node_modules
npm install
```

**ChromaDB Error?**
```powershell
# Delete and recreate database
cd backend
rm -r chroma_db
# Restart backend - will auto-recreate
```

---

## 📊 Project Structure

```
5_Roast_google_reviews/
├── backend/              # FastAPI + ChromaDB
│   ├── app/
│   │   ├── main.py      # API endpoints
│   │   ├── processor.py # Core pipeline
│   │   ├── llm.py       # LLM router
│   │   ├── memory.py    # ChromaDB
│   │   └── schemas.py   # Pydantic models
│   ├── chroma_db/       # Vector database
│   └── requirements.txt
│
├── frontend/            # Next.js 16 + Supabase
│   ├── src/
│   │   ├── app/         # Pages
│   │   ├── components/  # UI components
│   │   └── lib/         # Supabase clients
│   └── package.json
│
└── chatgpt_reviews.csv  # Sample data (124 MB)
```

---

## 🎯 Quick Start (TL;DR)

```powershell
# Terminal 1 - Backend
cd backend; .\venv\Scripts\activate; uvicorn app.main:app --reload

# Terminal 2 - Frontend
cd frontend; npm run dev

# Open: http://localhost:3000
```

---

**Built with 🔥 by Kushal Raj G S**
