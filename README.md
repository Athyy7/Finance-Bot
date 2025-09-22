#  Finance Agent - AI Financial Assistant

A powerful AI-driven financial assistant built with FastAPI backend and React frontend. Features intelligent conversation capabilities, financial data analysis, and comprehensive user profile management.

## ✨ Features

- ** AI-Powered Chat**: Streaming conversations with Anthropic Claude
- ** Financial Analysis**: Portfolio analysis, investment insights, and risk assessment
- ** User Profiles**: Access detailed financial information for any user
- ** Smart Calculations**: Built-in calculator for financial computations
- ** Data Management**: Automatic MongoDB seeding with financial datasets
- ** Real-time Streaming**: Server-sent events for responsive chat experience

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **Node.js 16+**
- **MongoDB** (running locally on default port 27017)
- **Anthropic API Key** (required)

### 1. Environment Setup

Create a `.env` file in the project root:

```bash
# Required - Get from https://console.anthropic.com/
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Optional - Use dummy values if you don't have these
OPENAI_API_KEY=dummy_openai_key
PINECONE_API_KEY=dummy_pinecone_key
```

> **Note**: Only the Anthropic API key is required. The Agent will work without OpenAI and Pinecone keys - just use dummy values for now. Make sure that you have these fields in .env

### 2. Backend Setup & Run

```bash
# Install Python dependencies
pip install -r requirements.txt

# Start the backend server
uvicorn backend.main:app --reload
```

The backend will:
- ✅ Connect to MongoDB
- ✅ Automatically seed financial data (500 user records)
- ✅ Start the API server on http://localhost:8000

### 3. Frontend Setup & Run

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

The frontend will be available at http://localhost:5173

## 🗄️ Database

### Automatic Data Seeding

When you start the application for the first time, it automatically:

1. **Creates MongoDB collections**
2. **Seeds financial data** from `data/financial_data.json`
3. **Creates indexes** for optimal query performance

**Database Details:**
- **Database Name**: `finance_bot`
- **Collection**: `financial_data_collection`
- **Records**: 500 user financial profiles
- **Connection**: `mongodb://localhost:27017`

### Sample User IDs

Try these User IDs in the chat:
- `U1000` - 27yr old from Canada, Low risk tolerance
- `U1001` - 49yr old from UK, ETF investor
- `U1002` - Various other profiles available

## 🔧 API Endpoints

### Main Endpoints
- **GET** `/` - API information
- **GET** `/health` - Health check
- **POST** `/api/v1/chat/stream` - Streaming chat endpoint

### Database Management
- **GET** `/database/status` - Check database seeding status
- **POST** `/database/seed` - Manually trigger data seeding

### Documentation
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 🤖 Chat Features

### Available Tools

The AI assistant has access to powerful tools:

**🧮 Calculator**
```
"Calculate compound interest on $10,000 at 7% for 5 years"
```

**👤 Get User Information**
```
"Show me the financial profile for user U1000"
"What's the investment strategy for user U1001?"
```

### Example Queries

- *"What's the financial profile of user U1000?"*
- *"Calculate the ROI on a $50,000 investment at 8% annually for 5 years"*
- *"Analyze the risk profile for user U1002"*
- *"What investment recommendations would you make for user U1001?"*

## 🛠️ Development

### Project Structure

```
finance_bot/
├── backend/
│   ├── app/
│   │   ├── apis/          # FastAPI routes
│   │   ├── services/      # Business logic
│   │   ├── tools/         # AI agent tools
│   │   ├── prompts/       # AI prompts
│   │   └── config/        # Database & settings
│   └── main.py           # FastAPI application
├── frontend/
│   └── src/              # React application
├── data/
│   └── financial_data.json  # Seed data
└── requirements.txt      # Python dependencies
```

### Adding New Tools

1. Create tool in `backend/app/tools/implementations/`
2. Register in `backend/app/tools/registry/tool_registry.py`
3. Tool automatically becomes available to the AI agent

## 🔍 Verification

### Check Database Status
Visit: http://localhost:8000/database/status

### Test Chat Interface
Visit: http://localhost:5173 and try:
- "Hello! What can you help me with?"
- "Show me user U1000's profile"

### Check Logs
Monitor the terminal for:
- Database connection status
- Data seeding progress
- Tool execution logs

## ⚠️ Troubleshooting

### MongoDB Connection Issues
```bash
# Make sure MongoDB is running
mongosh
# Should connect without errors
```

### Missing API Keys
- Only `ANTHROPIC_API_KEY` is required
- Other keys can be dummy values: `dummy_key_value`

### Port Conflicts
- Backend: Change port in uvicorn command: `--port 8001`
- Frontend: Vite will automatically suggest alternative ports

## 📝 Environment Variables Reference

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | ✅ Yes | Anthropic Claude API key | `sk-ant-...` |
| `OPENAI_API_KEY` | ❌ No | OpenAI API key (future use) | `sk-...` or `dummy` |
| `PINECONE_API_KEY` | ❌ No | Pinecone vector DB key (future use) | `abc123` or `dummy` |

---

## 🚀 Ready to Go!

1. Set up your `.env` with Anthropic API key
2. Start backend: `uvicorn backend.main:app --reload`
3. Start frontend: `cd frontend && npm run dev`
4. Open http://localhost:5173 and start chatting!

The AI assistant is ready to help with financial analysis, user data retrieval, and intelligent calculations. 🎉
