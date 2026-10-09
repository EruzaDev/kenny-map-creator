#!/usr/bin/env python3
"""ROS 2 Jazzy occupancy-grid/TF bridge. Never publishes motor commands."""
import argparse
import math
import sys
import threading
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT.parent/'Kenny---Automotive-self-driving-trash-can'))


class MappingSource:
    def __init__(self):
        self.lock=threading.Lock();self.grid=None;self.pose=None;self.updated=0.;self.revision=0
    def update_map(self,grid):
        with self.lock:
            self.grid=grid;self.updated=time.time();self.revision+=1
    def update_pose(self,pose):
        with self.lock:self.pose=pose;self.revision+=1
    def snapshot(self):
        with self.lock:
            if self.grid is None:return None
            return {'type':'map','revision':self.revision,'grid':self.grid,'pose':self.pose,'map_age_seconds':time.time()-self.updated}


def yaw(q):
    return math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--map-topic',default='/map');parser.add_argument('--map-frame',default='map');parser.add_argument('--base-frame',default='base_link')
    parser.add_argument('--fixture',help='Replay fixture environment.json without ROS for browser verification')
    args=parser.parse_args();source=MappingSource()
    if args.fixture:
        import json
        from kenny_rl.environment import validate_environment
        env=validate_environment(json.loads(Path(args.fixture).read_text()))
        source.update_map(env['grid']);source.update_pose([*env['start'],0])
        def replay():
            while True:
                source.update_map(env['grid']);time.sleep(1)
        threading.Thread(target=replay,daemon=True).start()
    else:
        try:
            import rclpy
            from rclpy.node import Node
            from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
            from nav_msgs.msg import OccupancyGrid
            from tf2_ros import Buffer, TransformListener, TransformException
        except ImportError as e:
            parser.error(f'ROS 2 is unavailable. Source /opt/ros/jazzy/setup.bash first. {e}')
        rclpy.init()
        class Bridge(Node):
            def __init__(self):
                super().__init__('kenny_editor_bridge')
                self.buffer=Buffer();self.listener=TransformListener(self.buffer,self)
                qos=QoSProfile(depth=1,reliability=ReliabilityPolicy.RELIABLE,durability=DurabilityPolicy.TRANSIENT_LOCAL)
                self.sub=self.create_subscription(OccupancyGrid,args.map_topic,self.map_callback,qos)
                self.create_timer(.5,self.pose_callback)
            def map_callback(self,msg):
                if msg.header.frame_id!=args.map_frame:
                    self.get_logger().error('Map frame differs from configured map frame');return
                if msg.info.width*msg.info.height>4_000_000:
                    self.get_logger().error('Map exceeds 4 million cells');return
                p=msg.info.origin.position
                data=[-1 if v<0 else 100 if v>=65 else 0 if v<=19 else -1 for v in msg.data]
                source.update_map({'width':msg.info.width,'height':msg.info.height,'resolution':msg.info.resolution,'origin':[p.x,p.y,yaw(msg.info.origin.orientation)],'data':data})
            def pose_callback(self):
                try:
                    tf=self.buffer.lookup_transform(args.map_frame,args.base_frame,rclpy.time.Time())
                    age=(self.get_clock().now().nanoseconds-(tf.header.stamp.sec*1_000_000_000+tf.header.stamp.nanosec))/1e9
                    if age>2:
                        source.update_pose(None);return
                    p=tf.transform.translation;source.update_pose([p.x,p.y,yaw(tf.transform.rotation)])
                except TransformException:source.update_pose(None)
        node=Bridge();threading.Thread(target=lambda:rclpy.spin(node),daemon=True).start()
    try:
        import uvicorn
        from backend.main import app
    except ImportError:
        from backend.server import serve
        serve(args.host,args.port,source)
    else:
        app.state.mapping_source=source;uvicorn.run(app,host=args.host,port=args.port)


if __name__=='__main__':main()
