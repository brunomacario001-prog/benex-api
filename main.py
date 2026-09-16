from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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
    if not payload.texto:
        raise HTTPException(status_code=400, detail="texto vazio")

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

@app.post("/webhook/whatsapp/{client_id}")
def webhook_whatsapp(client_id: str, payload: dict):
    return {"client_id": client_id, "recebido": True, "payload_keys": list(payload.keys())}


def tokenizar(comando: str):
    lexer = shlex.shlex(comando, posix=True, punctuation_chars="|&><;")
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def resolver_arquivo(nome: str, diretorio: Path):
    caminho = Path(nome).expanduser()
    if not caminho.is_absolute():
        caminho = diretorio / caminho
    return caminho.resolve()


def executar_pipeline(tokens, diretorio: Path):
    # Redirecionamento de saída suportado no final: > arquivo ou >> arquivo.
    modo_saida = None
    arquivo_saida = None

    for operador in (">>", ">"):
        if operador in tokens:
            indice = tokens.index(operador)
            if indice == 0 or indice != len(tokens) - 2:
                raise HTTPException(status_code=400, detail=f"uso inválido de {operador}")
            modo_saida = operador
            arquivo_saida = resolver_arquivo(tokens[indice + 1], diretorio)
            tokens = tokens[:indice]
            break

    if ">" in tokens or ">>" in tokens:
        raise HTTPException(status_code=400, detail="redirecionamento múltiplo não suportado")

    segmentos = []
    atual = []
    for token in tokens:
        if token == "|":
            if not atual:
                raise HTTPException(status_code=400, detail="pipe inválido")
            segmentos.append(atual)
            atual = []
        else:
            atual.append(token)

    if not atual:
        raise HTTPException(status_code=400, detail="pipe inválido")
    segmentos.append(atual)

    processos = []
    entrada_anterior = None

    try:
        for i, segmento in enumerate(segmentos):
            if not segmento:
                raise HTTPException(status_code=400, detail="comando vazio no pipeline")
            if segmento[0] == "cd":
                raise HTTPException(status_code=400, detail="cd não pode ser usado dentro de pipe")

            processo = subprocess.Popen(
                segmento,
                cwd=str(diretorio),
                stdin=entrada_anterior,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False
            )

            if entrada_anterior is not None:
                entrada_anterior.close()

            processos.append(processo)
            entrada_anterior = processo.stdout

        saida, erro_final = processos[-1].communicate(timeout=30)

        erros = []
        for processo in processos[:-1]:
            try:
                _, erro = processo.communicate(timeout=30)
            except ValueError:
                processo.wait(timeout=30)
                erro = processo.stderr.read() if processo.stderr else ""
            if erro:
                erros.append(erro)

        if erro_final:
            erros.append(erro_final)

        codigo = processos[-1].returncode

        if modo_saida:
            arquivo_saida.parent.mkdir(parents=True, exist_ok=True)
            modo = "a" if modo_saida == ">>" else "w"
            with open(arquivo_saida, modo, encoding="utf-8") as arquivo:
                arquivo.write(saida)
            saida = ""

        return codigo, saida, "".join(erros)

    except subprocess.TimeoutExpired:
        for processo in processos:
            if processo.poll() is None:
                processo.kill()
        raise


def executar_simples(tokens, diretorio: Path):
    if not tokens:
        raise HTTPException(status_code=400, detail="comando vazio")

    if tokens[0] == "cd":
        if len(tokens) > 2:
            raise HTTPException(status_code=400, detail="uso: cd [diretório]")

        if len(tokens) == 1:
            novo = Path.home()
        else:
            destino = Path(tokens[1]).expanduser()
            novo = destino if destino.is_absolute() else diretorio / destino

        novo = novo.resolve()
        if not novo.exists():
            raise HTTPException(status_code=404, detail="diretório não encontrado")
        if not novo.is_dir():
            raise HTTPException(status_code=400, detail="o destino não é um diretório")

        return 0, "", "", novo

    codigo, saida, erro = executar_pipeline(tokens, diretorio)
    return codigo, saida, erro, diretorio


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

        tokens = tokenizar(comando)
        if not tokens:
            raise HTTPException(status_code=400, detail="comando vazio")

        # Divide a linha em blocos ligados por &&. O próximo bloco só roda
        # quando o anterior termina com código 0, sem ativar shell=True.
        blocos = []
        bloco = []
        for token in tokens:
            if token == "&&":
                if not bloco:
                    raise HTTPException(status_code=400, detail="uso inválido de &&")
                blocos.append(bloco)
                bloco = []
            elif token == ";" or token == "||" or token == "&":
                raise HTTPException(status_code=400, detail=f"operador {token} ainda não suportado")
            else:
                bloco.append(token)

        if not bloco:
            raise HTTPException(status_code=400, detail="uso inválido de &&")
        blocos.append(bloco)

        saida_total = []
        erro_total = []
        codigo = 0

        for bloco in blocos:
            codigo, saida, erro, diretorio_atual = executar_simples(bloco, diretorio_atual)
            if saida:
                saida_total.append(saida)
            if erro:
                erro_total.append(erro)
            if codigo != 0:
                break

        return {
            "comando": comando,
            "codigo": codigo,
            "saida": "".join(saida_total),
            "erro": "".join(erro_total),
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
