"""Persistent media jobs: image generation via ComfyUI, video as animated still-image storyboard."""
import asyncio
import os
import sqlite3
import time
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

ROOT=Path("/data/media"); ROOT.mkdir(parents=True,exist_ok=True)
DATABASE="/data/media.sqlite3"
COMFY=os.getenv("COMFYUI_URL","").rstrip("/")
CHECKPOINT=os.getenv("COMFYUI_CHECKPOINT","")
MAX_W=int(os.getenv("MEDIA_MAX_WIDTH","768"))
MAX_H=int(os.getenv("MEDIA_MAX_HEIGHT","768"))
TIMEOUT=int(os.getenv("MEDIA_JOB_TIMEOUT","900"))
router=APIRouter(prefix="/api/media")

def db():
    return sqlite3.connect(DATABASE,timeout=30)

def setup():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,kind TEXT,prompt TEXT,width INTEGER,height INTEGER,
        scenes INTEGER,seconds INTEGER,status TEXT,progress INTEGER,
        error TEXT,result TEXT,created REAL,updated REAL)""")
        conn.execute("UPDATE jobs SET status='queued',progress=0 WHERE status='running'")

def details(jobid):
    with db() as conn:
        conn.row_factory=sqlite3.Row
        row=conn.execute("SELECT * FROM jobs WHERE id=?",(jobid,)).fetchone()
        return dict(row) if row else None

def update(jobid,**kwargs):
    with db() as conn:
        kwargs["updated"]=time.time()
        conn.execute("UPDATE jobs SET "+", ".join(k+"=?" for k in kwargs)+" WHERE id=?",
                     [*kwargs.values(),jobid])

class Request(BaseModel):
    kind: str
    prompt: str=Field(min_length=3,max_length=2000)
    width: int=512
    height: int=512
    scenes: int=Field(default=4,ge=2,le=12)
    seconds: int=Field(default=20,ge=4,le=120)

@router.get("/status")
async def media_status():
    if not COMFY: return {"configured":False,"online":False,"message":"Configure COMFYUI_URL"}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp=await client.get(COMFY+"/system_stats")
        return {"configured":bool(CHECKPOINT),"online":resp.is_success}
    except Exception:
        return {"configured":bool(CHECKPOINT),"online":False}

@router.post("/jobs")
async def submit(req:Request):
    if req.kind not in ("image","video"):raise HTTPException(400,"Tipo inválido")
    if req.width%64 or req.height%64 or not(256<=req.width<=MAX_W and 256<=req.height<=MAX_H):
        raise HTTPException(400,f"Dimensões inválidas: máximo {MAX_W}x{MAX_H}, múltiplos de 64")
    if not COMFY or not CHECKPOINT:raise HTTPException(503,"Configure COMFYUI_URL e COMFYUI_CHECKPOINT")
    jid=str(uuid.uuid4())
    with db() as conn:
        conn.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(
            jid,req.kind,req.prompt,req.width,req.height,req.scenes,req.seconds,
            "queued",0,"","",time.time(),time.time()))
    return {"id":jid,"status":"queued"}

@router.get("/jobs")
async def list_jobs():
    with db() as conn:
        conn.row_factory=sqlite3.Row
        return {"jobs":[dict(r) for r in conn.execute("SELECT * FROM jobs ORDER BY created DESC LIMIT 50")]}

@router.post("/jobs/{jid}/cancel")
async def cancel(jid:str):
    job=details(jid)
    if not job:raise HTTPException(404,"Tarefa inexistente")
    if job["status"] in ("queued","running"):update(jid,status="canceled",error="Cancelado pelo usuário")
    return {"ok":True}

@router.get("/jobs/{jid}/file")
async def get_file(jid:str):
    job=details(jid)
    if not job or job["status"]!="done":raise HTTPException(404,"Arquivo não está pronto")
    name="image.png" if job["kind"]=="image" else "video.mp4"
    path=ROOT/jid/name
    if not path.is_file():raise HTTPException(404,"Arquivo ausente")
    return FileResponse(path,filename=name)

def workflow(prompt,w,h,seed):
    return {
     "3":{"class_type":"KSampler","inputs":{"seed":seed,"steps":16,"cfg":6,"sampler_name":"euler","scheduler":"normal","denoise":1,"model":["4",0],"positive":["6",0],"negative":["7",0],"latent_image":["5",0]}},
     "4":{"class_type":"CheckpointLoaderSimple","inputs":{"ckpt_name":CHECKPOINT}},
     "5":{"class_type":"EmptyLatentImage","inputs":{"width":w,"height":h,"batch_size":1}},
     "6":{"class_type":"CLIPTextEncode","inputs":{"text":prompt,"clip":["4",1]}},
     "7":{"class_type":"CLIPTextEncode","inputs":{"text":"blur, low resolution, watermark, illegible text, artifacts","clip":["4",1]}},
     "8":{"class_type":"VAEDecode","inputs":{"samples":["3",0],"vae":["4",2]}},
     "9":{"class_type":"SaveImage","inputs":{"filename_prefix":"myai","images":["8",0]}}
    }

async def render_image(client,job,prompt,out,i):
    jid=job["id"]
    response=await client.post(COMFY+"/prompt",json={"prompt":workflow(prompt,job["width"],job["height"],int(time.time()*1000)%2147483647+i)})
    if not response.is_success:raise RuntimeError("ComfyUI rejeitou o pedido: "+response.text[:200])
    pid=response.json()["prompt_id"]
    start=time.monotonic()
    while time.monotonic()-start<TIMEOUT:
        if details(jid)["status"]=="canceled":raise RuntimeError("Cancelado; o ComfyUI pode continuar processando a cena atual")
        response=await client.get(COMFY+"/history/"+pid)
        response.raise_for_status()
        hist=response.json().get(pid)
        if hist:
            if hist.get("status",{}).get("status_str")=="error":
                raise RuntimeError("Falha no ComfyUI: confira logs e memória de vídeo")
            images=[x for v in hist.get("outputs",{}).values() for x in v.get("images",[])]
            if images:
                img=images[0]
                r=await client.get(COMFY+"/view",params={"filename":img["filename"],"subfolder":img.get("subfolder",""),"type":img.get("type","output")})
                r.raise_for_status()
                if len(r.content)>25_000_000:raise RuntimeError("Imagem excede 25 MB")
                out.write_bytes(r.content);return
        await asyncio.sleep(3)
    raise RuntimeError("Tempo limite do ComfyUI excedido")

async def run_ffmpeg(args,timeout):
    proc=await asyncio.create_subprocess_exec(*args,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.PIPE)
    try:
        _,error=await asyncio.wait_for(proc.communicate(),timeout)
    except asyncio.TimeoutError:
        proc.kill();await proc.wait()
        raise RuntimeError("Tempo limite do FFmpeg excedido")
    if proc.returncode:raise RuntimeError("Erro FFmpeg: "+error.decode(errors="replace")[-250:])

async def build_video(folder,images,seconds):
    # MVP: motion effects on still frames, not AI-generated moving characters.
    clip_duration=max(1,seconds//len(images))
    clips=[]
    for i,img in enumerate(images):
        dest=folder/f"clip{i:02}.mp4"
        await run_ffmpeg(["ffmpeg","-hide_banner","-loglevel","error","-y","-loop","1","-framerate","24",
          "-i",str(img),"-t",str(clip_duration),"-vf","scale=768:768:force_original_aspect_ratio=increase,crop=768:768,format=yuv420p",
          "-r","24","-c:v","libx264","-preset","ultrafast","-crf","26",str(dest)],150)
        clips.append(dest)
    listing=folder/"concat.txt"
    listing.write_text("".join(f"file '{item.name}'\n" for item in clips))
    final=folder/"video.mp4"
    await run_ffmpeg(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","concat","-safe","0",
        "-i",str(listing),"-c","copy",str(final)],90)
    return final

async def generate(job):
    folder=ROOT/job["id"];folder.mkdir(exist_ok=True)
    count=1 if job["kind"]=="image" else job["scenes"]
    outputs=[]
    async with httpx.AsyncClient(timeout=60) as client:
        for i in range(count):
            if details(job["id"])["status"]=="canceled":return
            out=folder/("image.png" if count==1 else f"frame{i:02}.png")
            prompt=job["prompt"] if count==1 else f"{job['prompt']}. Scene {i+1} of {count}, coherent storyboard, cinematic framing."
            await render_image(client,job,prompt,out,i)
            outputs.append(out)
            update(job["id"],progress=int(85*(i+1)/count))
    if details(job["id"])["status"]=="canceled":return
    if job["kind"]=="video":await build_video(folder,outputs,job["seconds"])
    if details(job["id"])["status"]!="canceled":
        update(job["id"],status="done",progress=100,result="image.png" if count==1 else "video.mp4")

async def worker():
    setup()
    while True:
        try:
            with db() as conn:
                conn.row_factory=sqlite3.Row
                row=conn.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if row:
                job=dict(row)
                update(job["id"],status="running",progress=1)
                try:await generate(job)
                except Exception as exc:
                    if details(job["id"])["status"]!="canceled":
                        update(job["id"],status="failed",error=str(exc)[:400])
            else:await asyncio.sleep(2)
        except asyncio.CancelledError:raise
        except Exception:
            await asyncio.sleep(5)
