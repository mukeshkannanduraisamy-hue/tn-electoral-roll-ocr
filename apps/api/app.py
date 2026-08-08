import os
import gradio as gr
from app.main import app as fastapi_app

demo = gr.Interface(
    fn=lambda: "Tamil Nadu Electoral Roll OCR System is Live!",
    inputs=[],
    outputs="text",
    title="TN Electoral Roll OCR System",
    description="FastAPI + React Web Application running on Hugging Face Spaces with Supabase PostgreSQL."
)

app = gr.mount_gradio_app(fastapi_app, demo, path="/status")

port = int(os.environ.get("PORT", 7860))
uvicorn.run(app, host="0.0.0.0", port=port)
