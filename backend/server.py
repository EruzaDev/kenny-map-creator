"""Dependency-light HTTP/WebSocket adapter for offline development.
Uses the same services as FastAPI. No robot command endpoints are exposed.
"""
import argparse
import base64
import hashlib
import json
import mimetypes
from pathlib import Path
import socket
import struct
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, parse_qs, urlsplit

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT.parent/'Kenny---Automotive-self-driving-trash-can'))
sys.path.insert(0,str(ROOT))
from backend.services import export_bundle, import_grid, marker_pdf, marker_image, png
from kenny_rl.environment import validate_environment
from backend.navigation import models, simulate


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def respond(self,body,status=200,content_type='application/json',filename=None):
        if isinstance(body,(dict,list)): body=json.dumps(body,allow_nan=False).encode()
        self.send_response(status);self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        if filename:self.send_header('Content-Disposition',f'attachment; filename={filename}')
        self.end_headers();self.wfile.write(body)
    def do_GET(self):
        path=unquote(self.path.split('?')[0])
        if path=='/api/live':return self.websocket()
        if path=='/api/models':return self.respond(models())
        if path.startswith('/api/markers/') and path.endswith('.png'):
            try:return self.respond(png(marker_image(int(path.split('/')[-1][:-4]),parse_qs(urlsplit(self.path).query).get('dictionary',['DICT_4X4_50'])[0])),content_type='image/png')
            except ValueError as e:return self.respond({'detail':str(e)},422)
        target=(ROOT/'dist'/('index.html' if path=='/' else path.lstrip('/'))).resolve()
        if not target.is_relative_to((ROOT/'dist').resolve()) or not target.is_file():
            return self.respond({'detail':'Not found. Run npm run build to create the editor.'},404)
        self.respond(target.read_bytes(),content_type=mimetypes.guess_type(target)[0] or 'application/octet-stream')
    def do_POST(self):
        try:
            length=int(self.headers.get('Content-Length',0))
            if not 0<length<=60_000_000:raise ValueError('Request size must be 1–60 MB')
            payload=json.loads(self.rfile.read(length))
            if self.path=='/api/simulate':return self.respond(simulate(payload))
            if self.path=='/api/export':return self.respond(export_bundle(payload),content_type='application/zip',filename='kenny-environment.zip')
            if self.path=='/api/import-map':return self.respond(import_grid(payload))
            if self.path=='/api/markers/pdf':
                validate_environment(payload)
                return self.respond(marker_pdf(payload['markers'],payload.get('markers_per_page',1),payload['dictionary']),content_type='application/pdf',filename='markers.pdf')
            self.respond({'detail':'Unknown API endpoint'},404)
        except (ValueError,KeyError,TypeError,OverflowError) as e:self.respond({'detail':str(e)},422)
        except Exception as e:
            self.log_error('Request failed: %s',e);self.respond({'detail':'Request failed; check server logs'},500)
    def websocket(self):
        key=self.headers.get('Sec-WebSocket-Key')
        if self.headers.get('Upgrade','').lower()!='websocket' or not key:
            return self.respond({'detail':'WebSocket upgrade required'},400)
        self.send_response(101);self.send_header('Upgrade','websocket');self.send_header('Connection','Upgrade')
        self.send_header('Sec-WebSocket-Accept',base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode());self.end_headers()
        self.close_connection=True
        def frame(data,opcode=1):
            size=len(data); header=bytes([128|opcode])
            header+=bytes([size]) if size<126 else bytes([126])+struct.pack('!H',size) if size<65536 else bytes([127])+struct.pack('!Q',size)
            self.connection.sendall(header+data)
        source=getattr(self.server,'mapping_source',None)
        try:
            if source is None:
                frame(json.dumps({'type':'status','connected':False,'message':'ROS bridge unavailable. Start ros/bridge.py on Kenny.'}).encode());frame(b'',8);return
            revision=-1
            while True:
                packet=source.snapshot()
                if packet and packet['revision']!=revision:
                    revision=packet['revision'];frame(json.dumps(packet,allow_nan=False).encode())
                elif not packet:
                    frame(json.dumps({'type':'status','connected':True,'message':'Waiting for /map and TF from Kenny'}).encode())
                time.sleep(1)
        except (BrokenPipeError,ConnectionResetError,OSError):return


def serve(host='127.0.0.1',port=8000,source=None):
    server=ThreadingHTTPServer((host,port),Handler);server.daemon_threads=True;server.mapping_source=source
    print(f'Kenny Environment Studio: http://{host}:{port}',flush=True)
    try:server.serve_forever()
    finally:server.server_close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args();serve(args.host,args.port)
