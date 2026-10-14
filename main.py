from fastapi import FastAPI

app = FastAPI(title="AI-HAS Helpdesk")

@app.get("/")
def home():
    return {
        "message": "AI-HAS backend is running!",
        "project": "AI-Powered Enterprise Helpdesk"
    }

@app.get("/health")
def health():
    return {"status": "healthy"}
