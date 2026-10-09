"""Shared generation and export services, independent of the HTTP adapter."""
import base64
import io
import json
import math
import zipfile
import cv2
import numpy as np
import yaml
from PIL import Image
from kenny_rl.environment import validate_environment, rasterize, load_environment, destination_goal
from pathlib import Path
from kenny_rl.config import RobotConfig

def marker_dictionary(name):
    limits={'DICT_4X4_50':50,'DICT_4X4_1000':1000}
    if name not in limits: raise ValueError('Unsupported marker dictionary')
    return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco,name)),limits[name]

def marker_image(mid, dictionary_name='DICT_4X4_50'):
    dictionary,limit=marker_dictionary(dictionary_name)
    if type(mid) is not int or not 0 <= mid < limit: raise ValueError(f'Marker ID must be 0–{limit-1}')
    marker=cv2.aruco.generateImageMarker(dictionary,mid,700)
    return Image.fromarray(np.pad(marker,100,constant_values=255))


def png(image):
    buf=io.BytesIO(); image.save(buf,format='PNG'); return buf.getvalue()


def marker_pdf(markers, per_page=1, dictionary_name='DICT_4X4_50'):
    """Vector A4 PDF with a selectable 1, 2, or 4 marker grid per sheet."""
    if not markers: raise ValueError('Place at least one marker')
    if per_page not in (1, 2, 4): raise ValueError('Markers per page must be 1, 2, or 4')
    mm=72/25.4; page_w=210*mm; page_h=297*mm
    margin=10*mm; header=23*mm; footer=15*mm; gap=6*mm
    cols=1 if per_page == 1 else 2
    rows=per_page // cols
    cell_w=(page_w-margin*2-gap*(cols-1))/cols
    cell_h=(page_h-margin-header-footer-gap*(rows-1))/rows
    contents=[]
    dictionary,limit=marker_dictionary(dictionary_name)
    for page_start in range(0, len(markers), per_page):
        page_markers=markers[page_start:page_start+per_page]
        commands=[]
        for slot,m in enumerate(page_markers):
            if type(m['id']) is not int or not 0 <= m['id'] < limit: raise ValueError('Marker ID outside selected dictionary')
            if not .01 <= m['size'] <= 1: raise ValueError('Printed side must be 0.01–1 meters')
            row=slot//cols; col=slot%cols
            x0=margin+col*(cell_w+gap); y0=footer+(rows-1-row)*(cell_h+gap)
            # A small fixed quiet zone makes every layout fit on one sheet.
            quiet=4*mm
            requested=m['size']*1000*mm
            size=min(requested, cell_w-quiet*2, cell_h-quiet*2-11*mm)
            bits=cv2.aruco.generateImageMarker(dictionary,m['id'],6)
            left=x0+(cell_w-size)/2; bottom=y0+12*mm+(cell_h-12*mm-size)/2
            module=size/6
            commands.extend([
                f'0.7 G 0.3 w {x0:.6f} {y0:.6f} {cell_w:.6f} {cell_h:.6f} re S',
                f'BT /F1 9 Tf {x0:.6f} {y0+3*mm:.6f} Td (ID {m["id"]} - black square: {size/mm:.1f} mm) Tj ET',
                '0 0 0 rg'
            ])
            for y in range(6):
                for x in range(6):
                    if bits[y,x] == 0:
                        px=left+x*module
                        py=bottom+(5-y)*module
                        commands.append(f'{px:.6f} {py:.6f} {module:.6f} {module:.6f} re f')
        commands.extend([
            f'BT /F1 11 Tf {margin:.6f} {page_h-12*mm:.6f} Td (KENNY / {dictionary_name} / {per_page} marker{"s" if per_page > 1 else ""} per page) Tj ET',
            f'BT /F1 8 Tf {margin:.6f} {page_h-18*mm:.6f} Td (Print at 100%, with fit-to-page disabled. The size above is the printed black square.) Tj ET',
            f'BT /F1 8 Tf {margin:.6f} {6*mm:.6f} Td (Calibration ruler: 50 mm) Tj ET',
            f'0 G 0.7 w {margin+42*mm:.6f} {7*mm:.6f} m {margin+92*mm:.6f} {7*mm:.6f} l S'
        ])
        contents.append(('\n'.join(commands)+'\n').encode('ascii'))
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    kids=[]
    for content in contents:
        page_id=len(objects)+1;stream_id=page_id+1;kids.append(f'{page_id} 0 R')
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_w:.6f} {page_h:.6f}] /Resources << /Font << /F1 3 0 R >> >> /Contents {stream_id} 0 R >>'.encode())
        objects.append(f'<< /Length {len(content)} >>\nstream\n'.encode()+content+b'endstream')
    objects[1]=f'<< /Type /Pages /Count {len(kids)} /Kids [{" ".join(kids)}] >>'.encode()
    output=bytearray(b'%PDF-1.4\n');offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(output));output.extend(f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n')
    start=len(output);output.extend(f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]:output.extend(f'{offset:010d} 00000 n \n'.encode())
    output.extend(f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode())
    return bytes(output)


def marker_pose(m):
    # OpenCV marker x right, y up, z out of printed face.
    # Floor: +z up. Wall: +z faces [cos(yaw),sin(yaw),0], +y up.
    yaw=m['yaw']
    if m['mount']=='floor': q=[0,0,math.sin(yaw/2),math.cos(yaw/2)]
    else:
        a=yaw+math.pi/2
        q=[math.cos(a/2)/math.sqrt(2),math.sin(a/2)/math.sqrt(2),math.sin(a/2)/math.sqrt(2),math.cos(a/2)/math.sqrt(2)]
    return {'id':m['id'],'size_m':m['size'],'position_m':[m['x'],m['y'],m['z']],'orientation_xyzw':q}


def export_bundle(env):
    validate_environment(env)
    env={**env,'goal':destination_goal(env)}
    load_environment(env,RobotConfig())
    grid=rasterize(env); g=env['grid']
    pixels=np.where(grid==100,0,np.where(grid==0,254,205)).astype(np.uint8)
    image=Image.fromarray(np.flipud(pixels)); imagebuf=io.BytesIO(); image.save(imagebuf,format='PPM')
    metadata={'image':'map.pgm','resolution':g['resolution'],'origin':g['origin'],'negate':0,'occupied_thresh':.65,'free_thresh':.196,'mode':'trinary'}
    markers={'map_id':env.get('name','kenny-environment'),'frame_id':'map','units':'meters','dictionary':env['dictionary'],'markers':[marker_pose(m) for m in env['markers']]}
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('environment.json',json.dumps(env,indent=2,allow_nan=False))
        z.writestr('map.pgm',imagebuf.getvalue()); z.writestr('map.yaml',yaml.safe_dump(metadata))
        z.writestr('markers.yaml',yaml.safe_dump(markers))
        destination=next((m for m in env['markers'] if m['id']==env.get('destination_marker_id')),None)
        navigation={'frame_id':'map','destination_marker_id':env.get('destination_marker_id'),
                    'goal_position_m':env['goal'],'near_goal_distance_m':5.0,
                    'destination_position_m':[destination['x'],destination['y']] if destination else env['goal'],
                    'near_goal_reference':'destination_marker' if destination else 'goal'}
        recording=Path(__file__).resolve().parent.parent/'res'/'im near.mp3'
        if recording.is_file():
            z.writestr('audio/im-near.mp3',recording.read_bytes())
            navigation['near_goal_audio']='audio/im-near.mp3'
        z.writestr('navigation.yaml',yaml.safe_dump(navigation))
        for m in env['markers']: z.writestr(f"markers/marker-{m['id']}.png",png(marker_image(m['id'],env['dictionary'])))
        if env['markers']: z.writestr('markers.pdf',marker_pdf(env['markers'],dictionary_name=env['dictionary']))
        z.writestr('README.txt','Load map.yaml with ROS 2 Nav2 map_server. markers.yaml is the application landmark database, not a Nav2 parameter file.\nSimulator: python -m kenny_rl.demo --environment environment.json --snapshot preview.png\nSimulator coordinates are map coordinates transformed by the inverse grid origin; padding is blocked. Physical navigation and localization nodes must consume the files separately.\n')
    return out.getvalue()


def import_grid(payload):
    meta=yaml.safe_load(payload['yaml'])
    raw=base64.b64decode(payload['image'],validate=True)
    if len(raw)>20_000_000: raise ValueError('Image exceeds 20 MB')
    im=Image.open(io.BytesIO(raw))
    if im.width*im.height>4_000_000: raise ValueError('Map exceeds 4 million cells')
    if meta.get('mode','trinary') != 'trinary': raise ValueError('Only trinary ROS maps are supported')
    free=meta.get('free_thresh',.196);occupied=meta.get('occupied_thresh',.65)
    if not 0 <= free < occupied <= 1: raise ValueError('Map thresholds must satisfy 0 <= free < occupied <= 1')
    im=im.convert('L')
    p=np.flipud(np.asarray(im)).astype(float)/255
    probability=p if meta.get('negate',0) else 1-p
    data=np.where(probability>meta.get('occupied_thresh',.65),100,np.where(probability<meta.get('free_thresh',.196),0,-1))
    grid={'width':im.width,'height':im.height,'resolution':meta['resolution'],'origin':meta['origin'],'data':data.ravel().tolist()}
    validate_environment({'version':1,'frame_id':'map','units':'meters','dictionary':'DICT_4X4_50','grid':grid,'markers':[],'obstacles':[],'start':[0,0],'goal':[0,0]})
    return grid
