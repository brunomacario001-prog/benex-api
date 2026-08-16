from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from datetime import datetime

app = FastAPI(
    title="BeneX API",
    description="API principal da startup BeneX - Python + FastAPI - benex.net.br",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS - libera seu frontend em benex.net.br e app.benex.net.br
origins = [
    "https://benex.net.br",
    "https://www.benex.net.br",
    "https://app.benex.net.br",
    "https://api.benex.net.br",
    "http://localhost:3000",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class IAModel(BaseModel):
    texto: str
    client_id: str = "default"

class AppModel(BaseModel):
    mensagem: str

@app.get("/")
def home():
    return {
        "startup": "BeneX",
        "dominio": "benex.net.br",
        "status": "online",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "docs": "https://api.benex.net.br/docs",
            "health": "https://api.benex.net.br/health",
            "ia": "https://api.benex.net.br/ia"
        }
    }

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "benex-api", "uptime": "running"}

@app.post("/ia")
def minha_ia(payload: IAModel):
    """
    Endpoint principal da sua IA.
    Aqui você coloca sua lógica Python.
    Hoje é um mock, amanhã você chama OpenAI, seu modelo treinado, etc.
    """
    if not payload.texto:
        raise HTTPException(status_code=400, detail="texto vazio")
    
    # TODO: Coloque sua IA aqui
    # Exemplo: resposta = meu_modelo.predict(payload.texto)
    resposta_mock = f"BeneX recebeu: '{payload.texto}' - client: {payload.client_id}"
    
    return {
        "client_id": payload.client_id,
        "pergunta": payload.texto,
        "resposta": resposta_mock,
        "modelo": "benex-v1-mock",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/app/status")
def app_status():
    return {
        "app": "BeneX App",
        "dominio": "app.benex.net.br",
        "api": "api.benex.net.br",
        "versao": "1.0.0"
    }

# Rota para quando crescer e tiver multi-cliente
@app.post("/webhook/whatsapp/{client_id}")
def webhook_whatsapp(client_id: str, payload: dict):
    # Deixa pronto pro futuro, sem usar agora
    return {"client_id": client_id, "recebido": True, "payload_keys": list(payload.keys())}