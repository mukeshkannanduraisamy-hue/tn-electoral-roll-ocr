import os
import uvicorn
import gradio as gr
from app.main import app as fastapi_app

demo = gr.Interface(
    fn=lambda: "Tamil Nadu Electoral Roll OCR System is Live!",
    inputs=[],
    outputs="text",
    title="TN Electoral Roll OCR System",
    description="FastAPI + React Web Application running on Hugging Face Spaces with Supabase PostgreSQL."
)

app = gr.mount_gradio_app(fastapi_app, demo, path="/")
