"""Local editor API. Run from the editor directory: uvicorn backend.main:app."""
import asyncio
from pathlib import Path
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from kenny_rl.environment import validate_environment
from .navigation import models, simulate, warm
from .services import marker_image, png, marker_pdf, export_bundle, import_grid
from .usb import usb_request
from .dispatch import tick, DispatchUnavailable, publish_simulation_pose
from .cloud_maps import remote_map, upload, CloudMapError
from .marker_optimization import optimize

app=FastAPI(title='Kenny Environment Editor')


@app.post('/api/cloud/map/{action}')
def cloud_map(action:str,payload:dict,request:Request):
    origin=request.headers.get('origin')
    if origin and origin!=str(request.base_url).rstrip('/'):
        raise HTTPException(403,'Commands require this editor origin')
    try:
        if action=='fetch':return remote_map()
        if action=='upload':return upload(payload)
        raise HTTPException(404,'Unknown cloud map action')
    except CloudMapError as e:raise HTTPException(e.status,str(e))
    except (ValueError,KeyError,TypeError) as e:raise HTTPException(422,str(e))


@app.post('/api/markers/optimize')
def optimize_markers(payload:dict):
    try:return optimize(payload)
    except (ValueError,KeyError,TypeError) as e:raise HTTPException(422,str(e))


@app.post('/api/dispatch/tick')
def receive_call(payload:dict,request:Request):
    origin=request.headers.get('origin')
    if origin and origin!=str(request.base_url).rstrip('/'):
        raise HTTPException(403,'Commands require this editor origin')
    try:return tick(payload)
    except DispatchUnavailable as e:raise HTTPException(503,str(e))
    except (ValueError,KeyError,TypeError) as e:raise HTTPException(422,str(e))


@app.post('/api/dispatch/pose')
def simulation_position(payload:dict,request:Request):
    origin=request.headers.get('origin')
    if origin and origin!=str(request.base_url).rstrip('/'):
        raise HTTPException(403,'Commands require this editor origin')
    try:return publish_simulation_pose(payload)
    except DispatchUnavailable as e:raise HTTPException(503,str(e))
    except (ValueError,KeyError,TypeError) as e:raise HTTPException(422,str(e))


@app.get('/api/usb/status')
def usb_status():
    try:return usb_request('status')
    except ValueError as e:raise HTTPException(503,str(e))


@app.post('/api/usb/{action}')
def usb_command(action:str,payload:dict,request:Request):
    origin=request.headers.get('origin')
    if origin and origin!=str(request.base_url).rstrip('/'):
        raise HTTPException(403,'USB commands require this editor origin')
    try:return usb_request(action,payload)
    except ValueError as e:raise HTTPException(422,str(e))


@app.get('/api/markers/{mid}.png')
def get_marker(mid:int, dictionary:str='DICT_4X4_50'):
    try: return Response(png(marker_image(mid,dictionary)),media_type='image/png')
    except ValueError as e: raise HTTPException(422,str(e))


@app.post('/api/markers/pdf')
def print_markers(env:dict):
    try:
        validate_environment(env)
        if not env.get('markers'): raise ValueError('Place at least one marker')
        return Response(marker_pdf(env['markers'],env.get('markers_per_page',1),env['dictionary']),media_type='application/pdf',headers={'Content-Disposition':'attachment; filename=markers.pdf'})
    except (ValueError,KeyError,TypeError) as e: raise HTTPException(422,str(e))


@app.post('/api/export')
def export(env:dict):
    try:
        return Response(export_bundle(env),media_type='application/zip',headers={'Content-Disposition':'attachment; filename=kenny-environment.zip'})
    except (ValueError,KeyError,TypeError,OverflowError) as e: raise HTTPException(422,str(e))


@app.post('/api/import-map')
def import_map(payload:dict):
    try:
        return import_grid(payload)
    except Exception as e: raise HTTPException(422,f'Invalid map: {e}')


@app.websocket('/api/live')
async def live(ws:WebSocket):
    await ws.accept()
    source=getattr(app.state,'mapping_source',None)
    try:
        if source is None:
            await ws.send_json({'type':'status','connected':False,'message':'ROS bridge unavailable. Start backend through ros/bridge.py on Kenny.'})
            await ws.close(); return
        revision=-1
        while True:
            packet=source.snapshot()
            if packet and packet['revision']!=revision:
                revision=packet['revision']; await ws.send_json(packet)
            elif packet is None:
                await ws.send_json({'type':'status','connected':True,'message':'Waiting for /map and TF from Kenny'})
            await asyncio.sleep(1)
    except (WebSocketDisconnect,RuntimeError): pass


DIST=Path(__file__).resolve().parent.parent/'dist'
if DIST.exists():
    app.mount('/assets',StaticFiles(directory=DIST/'assets'),name='assets')
    @app.get('/')
    def index(): return FileResponse(DIST/'index.html')


@app.get('/api/models')
def model_list():
    return models()


@app.post('/api/simulate')
def navigation_test(payload:dict):
    try:return simulate(payload)
    except (ValueError,KeyError,TypeError) as e:raise HTTPException(422,str(e))


@app.post('/api/simulate/warm')
def warm_model(payload:dict):
    try:return warm(payload)
    except (ValueError,KeyError,TypeError) as e:raise HTTPException(422,str(e))
