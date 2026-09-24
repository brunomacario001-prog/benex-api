from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import asyncio, fcntl, hmac, json, os, platform, pty, shlex, shutil, signal, struct, subprocess, termios, time, urllib.error, urllib.request
from pathlib import Path
INICIO_API=time.time()
app=FastAPI(title='BeneX API',description='API principal da startup BeneX - Python + FastAPI - benex.net.br',version='1.3.0',docs_url='/docs',redoc_url='/redoc')
origins=['https://benex.net.br','https://www.benex.net.br','https://app.benex.net.br','https://prompt.benex.net.br','https://api.benex.net.br','http://localhost:3000','http://localhost:5173']
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_credentials=True,allow_methods=['*'],allow_headers=['*'])
class IAModel(BaseModel): texto:str; client_id:str='default'
class TerminalModel(BaseModel): comando:str; token:str; diretorio:str='.'
def duracao(s):
 s=int(max(0,s)); d,s=divmod(s,86400); h,s=divmod(s,3600); m,s=divmod(s,60); return (f'{d}d ' if d else '')+(f'{h}h ' if h or d else '')+(f'{m}m ' if m or h or d else '')+f'{s}s'
def memoria():
 dados={}
 try:
  for linha in open('/proc/meminfo',encoding='utf-8'):
   k,v=linha.split(':',1); dados[k]=int(v.strip().split()[0])*1024
 except Exception: pass
 return dados.get('MemTotal',0),dados.get('MemAvailable',0)
@app.get('/')
def home(): return {'startup':'BeneX','status':'online','version':'1.3.0'}
@app.get('/health')
def health(): return {'status':'ok','service':'benex-api','uptime':duracao(time.time()-INICIO_API),'version':'1.3.0'}
@app.get('/system')
def system_status():
 total,disp=memoria(); uso=shutil.disk_usage(Path.cwd()); gb=1024**3
 return {'status':'ok','system':platform.system(),'release':platform.release(),'architecture':platform.machine(),'python':platform.python_version(),'cpu_logical':os.cpu_count() or 0,'memory':{'total_gb':round(total/gb,2),'available_gb':round(disp/gb,2),'used_percent':round((total-disp)/total*100,1) if total else 0},'disk':{'total_gb':round(uso.total/gb,2),'used_gb':round(uso.used/gb,2),'free_gb':round(uso.free/gb,2),'used_percent':round(uso.used/uso.total*100,1) if uso.total else 0},'uptime':duracao(time.time()-INICIO_API)}
@app.post('/ia')
def ia(p:IAModel): return {'client_id':p.client_id,'pergunta':p.texto,'resposta':f"BeneX recebeu: '{p.texto}' - client: {p.client_id}",'modelo':'benex-v1-mock','timestamp':datetime.now().isoformat()}
@app.get('/app/status')
def app_status(): return {'app':'BeneX App','api':'api.benex.net.br','versao':'1.3.0'}
def checar_url(url,timeout=8):
 inicio=time.perf_counter()
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'BeneX-Terminal/1.3'}),timeout=timeout) as r:return True,r.status,int((time.perf_counter()-inicio)*1000)
 except urllib.error.HTTPError as e:return False,e.code,int((time.perf_counter()-inicio)*1000)
 except Exception:return False,None,int((time.perf_counter()-inicio)*1000)
def executar_benex(t,cwd):
 if not t or t[0].lower()!='benex':return None
 sub=t[1].lower() if len(t)>1 else 'help'
 if len(t)>2:raise HTTPException(400,f'benex {sub} não recebe argumentos')
 if sub in ('help','ajuda','--help','-h'):return 0,'BeneX Terminal Administrativo v1.3\nComandos: status health site prompt services system disk env cwd python version help\n','',cwd
 if sub=='version':return 0,'BeneX Terminal Administrativo v1.3\n','',cwd
 if sub=='cwd':return 0,f'{cwd}\n','',cwd
 if sub=='python':return 0,f'Python {platform.python_version()}\n','',cwd
 if sub in ('health','site','prompt'):
  u={'health':'https://api.benex.net.br/health','site':'https://benex.net.br','prompt':'https://prompt.benex.net.br'}[sub];ok,code,ms=checar_url(u);ok=ok or(sub=='prompt' and code is not None and 200<=code<500);return 0 if ok else 1,f"{sub}: {'ONLINE' if ok else 'FALHA'} | HTTP {code or '---'} | {ms} ms\n",'',cwd
 if sub=='system':
  total,disp=memoria();gb=1024**3;return 0,f'Sistema: {platform.system()} {platform.release()}\nArquitetura: {platform.machine()}\nPython: {platform.python_version()}\nCPU lógica: {os.cpu_count()}\nMemória: total {total/gb:.2f} GB | disponível {disp/gb:.2f} GB\nUptime API: {duracao(time.time()-INICIO_API)}\n','',cwd
 if sub=='disk':
  u=shutil.disk_usage(cwd);gb=1024**3;return 0,f'Total: {u.total/gb:.2f} GB\nUsado: {u.used/gb:.2f} GB ({u.used/u.total*100:.1f}%)\nLivre: {u.free/gb:.2f} GB\n','',cwd
 if sub=='env':return 0,'Variáveis disponíveis (valores ocultos):\n'+'\n'.join(sorted(os.environ))+'\n','',cwd
 if sub in ('services','status'):
  linhas=[];falhas=0
  for n,u in [('API','https://api.benex.net.br/health'),('Site','https://benex.net.br'),('Prompt','https://prompt.benex.net.br')]:
   ok,code,ms=checar_url(u);ok=ok or(n=='Prompt' and code is not None and 200<=code<500);falhas+=not ok;linhas.append(f"{n:<8} {'OK' if ok else 'FALHA':<6} HTTP {code or '---'} {ms} ms")
  return 0 if not falhas else 1,'\n'.join(linhas)+'\n','',cwd
 raise HTTPException(400,f'comando BeneX desconhecido: {sub}')
def tokenizar(c):
 l=shlex.shlex(c,posix=True,punctuation_chars='|&><;');l.whitespace_split=True;l.commenters='';return list(l)
def pipeline(t,cwd):
 modo=arquivo=None
 for op in ('>>','>'):
  if op in t:
   i=t.index(op)
   if i==0 or i!=len(t)-2:raise HTTPException(400,f'uso inválido de {op}')
   modo=op;arquivo=(cwd/Path(t[i+1])).resolve();t=t[:i];break
 seg=[];at=[]
 for x in t:
  if x=='|':
   if not at:raise HTTPException(400,'pipe inválido')
   seg.append(at);at=[]
  else:at.append(x)
 if not at:raise HTTPException(400,'pipe inválido')
 seg.append(at);ps=[];entrada=None
 for s in seg:
  p=subprocess.Popen(s,cwd=str(cwd),stdin=entrada,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,shell=False)
  if entrada:entrada.close()
  ps.append(p);entrada=p.stdout
 out,err=ps[-1].communicate(timeout=30);code=ps[-1].returncode
 if modo:
  with open(arquivo,'a' if modo=='>>' else 'w',encoding='utf-8') as f:f.write(out)
  out=''
 return code,out,err
def executar(c,cwd):
 t=tokenizar(c)
 for op in (';','||','&'):
  if op in t:raise HTTPException(400,f'operador não suportado: {op}')
 b=executar_benex(t,cwd)
 if b:return b
 if t and t[0]=='cd':
  novo=(Path.home() if len(t)==1 else (cwd/Path(t[1]))).resolve()
  if not novo.is_dir():raise HTTPException(404,'diretório não encontrado')
  return 0,'','',novo
 code,out,err=pipeline(t,cwd);return code,out,err,cwd
def chave_valida(token):
 chave=os.getenv('BENEX_TERMINAL_KEY')
 return bool(chave and isinstance(token,str) and hmac.compare_digest(token,chave))
@app.post('/executar')
def executar_terminal(p:TerminalModel):
 if not chave_valida(p.token):raise HTTPException(401,'acesso não autorizado')
 try:
  cwd=Path(p.diretorio).expanduser().resolve();cwd=cwd if cwd.is_dir() else Path.cwd();code,out,err,novo=executar(p.comando.strip(),cwd);return {'codigo':code,'saida':out,'erro':err,'diretorio':str(novo)}
 except HTTPException:raise
 except Exception as e:raise HTTPException(500,f'erro interno: {type(e).__name__}')
def resize(fd,r,c):fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',r,c,0,0))
async def ler(ws,fd):
 while True:
  try:d=await asyncio.to_thread(os.read,fd,4096)
  except OSError:break
  if not d:break
  try:await ws.send_text(d.decode(errors='replace'))
  except Exception:break
@app.websocket('/terminal')
async def terminal(ws:WebSocket):
 if ws.headers.get('origin') not in origins:await ws.close(code=1008);return
 await ws.accept()
 try:
  autenticacao=json.loads(await asyncio.wait_for(ws.receive_text(),timeout=5))
  if not isinstance(autenticacao,dict) or autenticacao.get('type')!='auth' or not chave_valida(autenticacao.get('token')):
   await ws.close(code=1008);return
 except WebSocketDisconnect:return
 except (asyncio.TimeoutError,ValueError,TypeError):
  await ws.close(code=1008);return
 await ws.send_json({'type':'auth','ok':True})
 pid,fd=pty.fork()
 if pid==0:
  os.environ.update(TERM='xterm-256color',COLORTERM='truecolor',PS1='benex@servidor:\\w$ ',BENEX_CLI=str(Path(__file__).with_name('benex_cli.py')));shell='/bin/bash' if os.path.exists('/bin/bash') else '/bin/sh';os.execv(shell,[shell,'--noprofile','--rcfile',str(Path(__file__).with_name('.benexrc')),'-i'] if shell.endswith('bash') else [shell,'-i'])
 leitor=asyncio.create_task(ler(ws,fd));resize(fd,30,120)
 try:
  while True:
   m=json.loads(await ws.receive_text());tipo=m.get('type')
   if tipo=='input':await asyncio.to_thread(os.write,fd,m.get('data','').encode())
   elif tipo=='resize':resize(fd,max(2,min(int(m.get('rows',30)),200)),max(10,min(int(m.get('cols',120)),400)))
 except WebSocketDisconnect:pass
 finally:
  leitor.cancel()
  try:os.close(fd);os.kill(pid,signal.SIGHUP)
  except OSError:pass
