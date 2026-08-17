import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from routes import dashboard_routes, order_routes, twilio_routes

load_dotenv()

app = FastAPI(title="Voice Agent - Tacos El Güero")

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(dashboard_routes.router)
app.include_router(order_routes.router)
app.include_router(twilio_routes.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=True,
    )
