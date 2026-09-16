from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import asyncio
import fcntl
import json
import os
import platform
import pty
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import termios
import time
import urllib.error
import urllib.request
from pathlib import Path

INICIO_API = time.time()

app = FastAPI(
    title="BeneX API",
    description="API principal da startup BeneX - Python + FastAPI - benex.net.br",
    version="1.2.0",
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
            "ia": "https://api.benex.net.br/ia",
            "terminal_ws": "wss://api.benex.net.br/terminal"
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
        "versao": "1.2.0"
    }

@app.post("/webhook/whatsapp/{client_id}")
def webhook_whatsapp(client_id: str, payload: dict):
    return {"client_id": client_id, "recebido": True, "payload_keys": list(payload.keys())}


def formatar_duracao(segundos: float):
    total = int(max(0, segundos))
    dias, resto = divmod(total, 86400)
    horas, resto = divmod(resto, 3600)
    minutos, segundos = divmod(resto, 60)
    partes = []
    if dias:
        partes.append(f"{dias}d")
    if horas or dias:
        partes.append(f"{horas}h")
    if minutos or horas or dias:
        partes.append(f"{minutos}m")
    partes.append(f"{segundos}s")
    return " ".join(partes)


def checar_url(url: str, timeout=8):
    inicio = time.perf_counter()
    requisicao = urllib.request.Request(url, headers={"User-Agent": "BeneX-Terminal/1.2"})
    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            latencia = int((time.perf_counter() - inicio) * 1000)
            return True, resposta.status, latencia
    except urllib.error.HTTPError as erro:
        latencia = int((time.perf_counter() - inicio) * 1000)
        return False, erro.code, latencia
    except Exception:
        latencia = int((time.perf_counter() - inicio) * 1000)
        return False, None, latencia


def executar_benex(tokens, diretorio: Path):
    if not tokens or tokens[0].lower() != "benex":
        return None
    subcomando = tokens[1].lower() if len(tokens) > 1 else "help"
    argumentos = tokens[2:]
    if subcomando in ("help", "ajuda", "--help", "-h"):
        saida = """BeneX Terminal Administrativo v1.2

Comandos:
  benex status       resumo do ecossistema BeneX
  benex health       testa a API BeneX
  benex site         testa o site principal
  benex prompt       testa o terminal privado
  benex services     testa os principais serviços HTTP
  benex system       informações do servidor Render
  benex disk         uso de armazenamento do servidor
  benex env          lista apenas nomes das variáveis de ambiente
  benex cwd          mostra o diretório atual
  benex python       mostra a versão do Python
  benex version      mostra a versão administrativa
  benex help         mostra esta ajuda
"""
        return 0, saida, "", diretorio
    if argumentos:
        raise HTTPException(status_code=400, detail=f"benex {subcomando} não recebe argumentos")
    if subcomando == "version":
        return 0, "BeneX Terminal Administrativo v1.2\n", "", diretorio
    if subcomando == "cwd":
        return 0, f"{diretorio}\n", "", diretorio
    if subcomando == "python":
        return 0, f"Python {platform.python_version()}\n", "", diretorio
    if subcomando == "health":
        ok, codigo, ms = checar_url("https://api.benex.net.br/health")
        estado = "ONLINE" if ok else "FALHA"
        http = codigo if codigo is not None else "sem resposta"
        return (0 if ok else 1), f"API BeneX: {estado} | HTTP {http} | {ms} ms\n", "", diretorio
    if subcomando == "site":
        ok, codigo, ms = checar_url("https://benex.net.br")
        estado = "ONLINE" if ok else "FALHA"
        http = codigo if codigo is not None else "sem resposta"
        return (0 if ok else 1), f"Site BeneX: {estado} | HTTP {http} | {ms} ms\n", "", diretorio
    if subcomando == "prompt":
        ok, codigo, ms = checar_url("https://prompt.benex.net.br")
        alcancavel = ok or (codigo is not None and 200 <= codigo < 500)
        estado = "ALCANCAVEL" if alcancavel else "FALHA"
        http = codigo if codigo is not None else "sem resposta"
        return (0 if alcancavel else 1), f"Prompt privado: {estado} | HTTP {http} | {ms} ms\n", "", diretorio
    if subcomando == "services":
        servicos = [("API", "https://api.benex.net.br/health"), ("Site", "https://benex.net.br"), ("Prompt", "https://prompt.benex.net.br")]
        linhas, falhas = [], 0
        for nome, url in servicos:
            ok, codigo, ms = checar_url(url)
            if nome == "Prompt":
                ok = ok or (codigo is not None and 200 <= codigo < 500)
            if not ok:
                falhas += 1
            linhas.append(f"{nome:<8} {'OK' if ok else 'FALHA':<6} HTTP {codigo if codigo is not None else '---'}  {ms} ms")
        return (0 if falhas == 0 else 1), "\n".join(linhas) + "\n", "", diretorio
    if subcomando == "system":
        memoria = "indisponível"
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as arquivo:
                dados = {}
                for linha in arquivo:
                    chave, valor = linha.split(":", 1)
                    dados[chave] = valor.strip()
                memoria = f"total {dados.get('MemTotal', '?')} | disponível {dados.get('MemAvailable', '?')}"
        except Exception:
            pass
        saida = (f"Sistema: {platform.system()} {platform.release()}\n" f"Arquitetura: {platform.machine()}\n" f"Python: {platform.python_version()}\n" f"CPU lógica: {os.cpu_count() or 'indisponível'}\n" f"Memória: {memoria}\n" f"Diretório: {diretorio}\n" f"Uptime API: {formatar_duracao(time.time() - INICIO_API)}\n")
        return 0, saida, "", diretorio
    if subcomando == "disk":
        uso = shutil.disk_usage(diretorio)
        gb = 1024 ** 3
        percentual = (uso.used / uso.total * 100) if uso.total else 0
        saida = (f"Disco em {diretorio}\n" f"Total: {uso.total / gb:.2f} GB\n" f"Usado: {uso.used / gb:.2f} GB ({percentual:.1f}%)\n" f"Livre: {uso.free / gb:.2f} GB\n")
        return 0, saida, "", diretorio
    if subcomando == "env":
        nomes = sorted(os.environ.keys())
        return 0, "Variáveis disponíveis (valores ocultos):\n" + "\n".join(nomes) + "\n", "", diretorio
    if subcomando == "status":
        ok_api, codigo_api, ms_api = checar_url("https://api.benex.net.br/health")
        ok_site, codigo_site, ms_site = checar_url("https://benex.net.br")
        ok_prompt, codigo_prompt, ms_prompt = checar_url("https://prompt.benex.net.br")
        ok_prompt = ok_prompt or (codigo_prompt is not None and 200 <= codigo_prompt < 500)
        def linha(nome, ok, codigo, ms):
            return f"{nome:<8} {'OK' if ok else 'FALHA':<6} HTTP {codigo if codigo is not None else '---'}  {ms} ms"
        saida = ("BeneX | Status Administrativo\n-----------------------------\n" + linha("API", ok_api, codigo_api, ms_api) + "\n" + linha("Site", ok_site, codigo_site, ms_site) + "\n" + linha("Prompt", ok_prompt, codigo_prompt, ms_prompt) + "\n" + f"Servidor  {platform.system()} {platform.machine()} | Python {platform.python_version()}\n" + f"Uptime    {formatar_duracao(time.time() - INICIO_API)}\n" + f"Diretório {diretorio}\n")
        return (0 if ok_api and ok_site and ok_prompt else 1), saida, "", diretorio
    raise HTTPException(status_code=400, detail=f"comando BeneX desconhecido: {subcomando}. Use: benex help")


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
    modo_saida, arquivo_saida = None, None
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
    segmentos, atual = [], []
    for token in tokens:
        if token == "|":
            if not atual:
                raise HTTPException(status_code=400, detail="pipe inválido")
            segmentos.append(atual); atual = []
        else:
            atual.append(token)
    if not atual:
        raise HTTPException(status_code=400, detail="pipe inválido")
    segmentos.append(atual)
    processos, entrada_anterior = [], None
    try:
        for segmento in segmentos:
            if segmento[0] == "cd":
                raise HTTPException(status_code=400, detail="cd não pode ser usado dentro de pipe")
            if segmento[0].lower() == "benex":
                raise HTTPException(status_code=400, detail="comandos benex não podem ser usados dentro de pipe")
            processo = subprocess.Popen(segmento, cwd=str(diretorio), stdin=entrada_anterior, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=False)
            if entrada_anterior is not None:
                entrada_anterior.close()
            processos.append(processo); entrada_anterior = processo.stdout
        saida, erro_final = processos[-1].communicate(timeout=30)
        erros = []
        for processo in processos[:-1]:
            try:
                _, erro = processo.communicate(timeout=30)
            except ValueError:
                processo.wait(timeout=30); erro = processo.stderr.read() if processo.stderr else ""
            if erro:
                erros.append(erro)
        if erro_final:
            erros.append(erro_final)
        codigo = processos[-1].returncode
        if modo_saida:
            arquivo_saida.parent.mkdir(parents=True, exist_ok=True)
            with open(arquivo_saida, "a" if modo_saida == ">>" else "w", encoding="utf-8") as arquivo:
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
    benex = executar_benex(tokens, diretorio)
    if benex is not None:
        return benex
    if tokens[0] == "cd":
        if len(tokens) > 2:
            raise HTTPException(status_code=400, detail="uso: cd [diretório]")
        novo = Path.home() if len(tokens) == 1 else (Path(tokens[1]).expanduser() if Path(tokens[1]).expanduser().is_absolute() else diretorio / Path(tokens[1]).expanduser())
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
        blocos, bloco = [], []
        for token in tokens:
            if token == "&&":
                if not bloco:
                    raise HTTPException(status_code=400, detail="uso inválido de &&")
                blocos.append(bloco); bloco = []
            elif token in (";", "||", "&"):
                raise HTTPException(status_code=400, detail=f"operador {token} ainda não suportado")
            else:
                bloco.append(token)
        if not bloco:
            raise HTTPException(status_code=400, detail="uso inválido de &&")
        blocos.append(bloco)
        saida_total, erro_total, codigo = [], [], 0
        for bloco in blocos:
            codigo, saida, erro, diretorio_atual = executar_simples(bloco, diretorio_atual)
            if saida: saida_total.append(saida)
            if erro: erro_total.append(erro)
            if codigo != 0: break
        return {"comando": comando, "codigo": codigo, "saida": "".join(saida_total), "erro": "".join(erro_total), "diretorio": str(diretorio_atual), "timestamp": datetime.now().isoformat()}
    except HTTPException:
        raise
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="comando não encontrado no servidor")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="comando excedeu 30 segundos")
    except Exception as erro:
        raise HTTPException(status_code=500, detail=str(erro))


def ajustar_tamanho_pty(fd: int, linhas: int, colunas: int):
    linhas = max(2, min(int(linhas), 500))
    colunas = max(2, min(int(colunas), 500))
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", linhas, colunas, 0, 0))


async def ler_pty(websocket: WebSocket, fd: int):
    loop = asyncio.get_running_loop()
    while True:
        try:
            dados = await loop.run_in_executor(None, os.read, fd, 4096)
            if not dados:
                break
            await websocket.send_text(dados.decode("utf-8", errors="replace"))
        except OSError:
            break


@app.websocket("/terminal")
async def terminal_websocket(websocket: WebSocket):
    origem = websocket.headers.get("origin")
    if origem not in origins:
        await websocket.close(code=1008, reason="Origem não autorizada")
        return

    await websocket.accept()
    pid = None
    fd = None
    tarefa_leitura = None

    try:
        pid, fd = pty.fork()
        if pid == 0:
            ambiente = os.environ.copy()
            ambiente["TERM"] = "xterm-256color"
            ambiente["COLORTERM"] = "truecolor"
            ambiente["PS1"] = r"benex@servidor:\w$ "
            shell = shutil.which("bash") or "/bin/sh"
            os.execvpe(shell, [shell, "--noprofile", "--norc", "-i"] if shell.endswith("bash") else [shell, "-i"], ambiente)

        ajustar_tamanho_pty(fd, 24, 80)
        tarefa_leitura = asyncio.create_task(ler_pty(websocket, fd))

        while True:
            mensagem = await websocket.receive_text()
            try:
                pacote = json.loads(mensagem)
            except json.JSONDecodeError:
                pacote = {"type": "input", "data": mensagem}

            tipo = pacote.get("type", "input")
            if tipo == "input":
                dados = str(pacote.get("data", "")).encode("utf-8")
                if dados:
                    os.write(fd, dados)
            elif tipo == "resize":
                ajustar_tamanho_pty(fd, pacote.get("rows", 24), pacote.get("cols", 80))
            elif tipo == "signal" and pacote.get("signal") == "SIGINT":
                os.killpg(pid, signal.SIGINT)

    except WebSocketDisconnect:
        pass
    finally:
        if tarefa_leitura:
            tarefa_leitura.cancel()
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if pid:
            try:
                os.kill(pid, signal.SIGHUP)
            except ProcessLookupError:
                pass
            try:
                os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                pass
