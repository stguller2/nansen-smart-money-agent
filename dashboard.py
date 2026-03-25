import os
import json
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI(title="Smart Money Intelligence Web Dashboard")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def read_dashboard(request: Request):
    """Serve the main dashboard page."""
    sig_path = "outputs/signals.json"
    holdings_path = "outputs/holdings.json"
    signals = []
    holdings = []
    
    if os.path.exists(sig_path):
        try:
            with open(sig_path, "r") as f:
                signals = json.load(f)
            signals.reverse()  # Show newest alerts first
        except Exception:
            pass
            
    if os.path.exists(holdings_path):
        try:
            with open(holdings_path, "r") as f:
                holdings = json.load(f)[:5] # Show top 5 holdings
        except Exception:
            pass
            
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "signals": signals[:48],
        "holdings": holdings
    })

@app.get("/api/signals")
async def api_get_signals():
    """Raw JSON endpoint for external tools/React."""
    sig_path = "outputs/signals.json"
    if os.path.exists(sig_path):
        try:
            with open(sig_path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []

if __name__ == "__main__":
    print("🚀 Starting Web Dashboard at: http://localhost:8000")
    uvicorn.run("dashboard:app", host="0.0.0.0", port=8000, reload=True)
