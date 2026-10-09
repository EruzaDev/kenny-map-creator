"""Render a downloaded navigation replay as a standalone animated GIF."""
import argparse
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def render(environment,replay,output):
    g=environment['grid'];origin=g['origin'];width=g['width']*g['resolution'];height=g['height']*g['resolution']
    scale=min(700/width,450/height);left=50;top=100
    font=ImageFont.load_default(size=16);heading=ImageFont.load_default(size=23)
    def point(p):
        x=p[0]-origin[0];y=p[1]-origin[1];c,s=math.cos(origin[2]),math.sin(origin[2])
        return (left+(c*x+s*y)*scale,top+(height-(-s*x+c*y))*scale)
    base=Image.new('RGB',(800,620),'#f4f8f5');d=ImageDraw.Draw(base)
    d.text((35,20),'KENNY / trained PPO navigation replay',font=heading,fill='#203f32')
    d.rectangle((left,top,left+width*scale,top+height*scale),fill='white',outline='#abc4b4',width=2)
    r=g['resolution']
    for row in range(g['height']):
        for col in range(g['width']):
            value=g['data'][row*g['width']+col]
            if value:
                x=left+col*r*scale;y=top+(height-(row+1)*r)*scale
                d.rectangle((x,y,x+r*scale,y+r*scale),fill='#46564e' if value==100 else '#b5bfba')
    for o in environment['obstacles']:
        corners=[[o['x'],o['y']],[o['x']+o['width'],o['y']],[o['x']+o['width'],o['y']+o['depth']],[o['x'],o['y']+o['depth']]]
        d.polygon([point(p) for p in corners],fill='#425e50' if o['kind']=='wall' else '#c89365')
    for m in environment['markers']:
        x,y=point([m['x'],m['y']]);d.rectangle((x-5,y-5,x+5,y+5),fill='#d6b630');d.text((x+8,y-8),str(m['id']),font=font,fill='#826d22')
    for label,p,color in [('START',environment['start'],'#129371'),('GOAL',environment['goal'],'#d48929')]:
        x,y=point(p);d.ellipse((x-8,y-8,x+8,y+8),fill=color);d.text((x+10,y+6),label,font=font,fill=color)
    d.text((35,565),'Green: traveled path   Blue: planned route   Orange: safety intervention',font=font,fill='#466050')
    d.text((35,593),f"Result: {replay['info']['event']} / distance {replay['info']['path_length']:.2f} m / guard interventions {replay['info']['interventions']}",font=font,fill='#466050')
    frames=[];indices=list(range(0,len(replay['frames']),5))
    if indices[-1]!=len(replay['frames'])-1:indices.append(len(replay['frames'])-1)
    for index in indices:
        f=replay['frames'][index];image=base.copy();draw=ImageDraw.Draw(image)
        draw.text((35,60),f"Step {f['step']} / {f['step']*replay['dt']:.1f} simulated seconds / {f['event']}",font=font,fill='#466050')
        route=[point(p) for p in f['route']]
        if len(route)>1:draw.line(route,fill='#619ac7',width=2)
        traveled=[point(p['pose']) for p in replay['frames'][:index+1]]
        if len(traveled)>1:draw.line(traveled,fill='#0b9970',width=3)
        x,y=point(f['pose']);radius=replay['robot_radius']*scale
        draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill='#e5a332' if f['intervened'] else '#119b73',outline='white',width=2)
        angle=f['pose'][2]-origin[2];draw.line((x,y,x+math.cos(angle)*(radius+8),y-math.sin(angle)*(radius+8)),fill='#245241',width=3)
        frames.append(image.convert('P',palette=Image.Palette.ADAPTIVE))
    frames[0].save(output,save_all=True,append_images=frames[1:],duration=[250]*(len(frames)-1)+[1500],loop=0,optimize=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--environment',required=True);p.add_argument('--replay',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();render(json.loads(Path(a.environment).read_text()),json.loads(Path(a.replay).read_text()),a.output)
