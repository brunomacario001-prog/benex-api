from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from datetime import datetime
import subprocess
import shlex
from pathlib import Path

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
    "https://prompt.benex.net.br",
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

class TerminalModel(BaseModel):
    comando: str
    diretorio: str = "."

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

@app.post("/executar")
def executar_terminal(payload: TerminalModel):
    comando = payload.comando.strip()

    if not comando:
        raise HTTPException(status_code=400, detail="comando vazio")

    try:
        if not payload.diretorio or payload.diretorio == ".":
            diretorio_atual = Path.cwd().resolve()
        else:
            diretorio_atual = Path(payload.diretorio).expanduser()
            if not diretorio_atual.is_absolute():
                diretorio_atual = Path.cwd() / diretorio_atual
            diretorio_atual = diretorio_atual.resolve()

        if not diretorio_atual.exists() or not diretorio_atual.is_dir():
            raise HTTPException(status_code=400, detail="diretório atual inválido")

        partes = shlex.split(comando)

        if not partes:
            raise HTTPException(status_code=400, detail="comando vazio")

        # cd é interno do shell; tratamos diretamente para manter o diretório
        # entre uma requisição do terminal e a próxima.
        if partes[0] == "cd":
            if len(partes) > 2:
                raise HTTPException(status_code=400, detail="uso: cd [diretório]")

            if len(partes) == 1:
                novo_diretorio = Path.home()
            else:
                destino = Path(partes[1]).expanduser()
                novo_diretorio = destino if destino.is_absolute() else diretorio_atual / destino

            novo_diretorio = novo_diretorio.resolve()

            if not novo_diretorio.exists():
                raise HTTPException(status_code=404, detail="diretório não encontrado")

            if not novo_diretorio.is_dir():
                raise HTTPException(status_code=400, detail="o destino não é um diretório")

            return {
                "comando": comando,
                "codigo": 0,
                "saida": "",
                "erro": "",
                "diretorio": str(novo_diretorio),
                "timestamp": datetime.now().isoformat()
            }

        resultado = subprocess.run(
            partes,
            cwd=str(diretorio_atual),
            capture_output=True,
            text=True,
            timeout=30,
            shell=False
        )

        return {
            "comando": comando,
            "codigo": resultado.returncode,
            "saida": resultado.stdout,
            "erro": resultado.stderr,
            "diretorio": str(diretorio_atual),
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="comando não encontrado no servidor")

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="comando excedeu 30 segundos")

    except Exception as erro:
        raise HTTPException(status_code=500, detail=str(erro))
