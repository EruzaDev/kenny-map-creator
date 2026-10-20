#!/usr/bin/env python3
"""ROS 2 Jazzy occupancy-grid/TF bridge. Never publishes motor commands."""
import argparse
import json
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
        self.map_revision=0;self.frame='map';self.pose_frame=None;self.pose_observed=0.
        self.pose_source='Unavailable';self.pose_error=None;self.uncertainty=None;self.scan=None
        self.session_id=str(time.time_ns())
        self.marker_observations=None;self.marker_observed=0.
        self.apply_callback=None;self.applied_map_sha256=None;self.tracking_error=None
        self.apply_lock=threading.Lock()
    def update_map(self,grid,frame='map'):
        with self.lock:
            self.grid=grid;self.frame=frame;self.updated=time.monotonic();self.revision+=1;self.map_revision+=1
    def update_pose(self,pose,frame=None,age=0.,source='SLAM + wheel encoders',uncertainty=None,error=None):
        with self.lock:
            if pose is not None:
                self.pose=list(pose);self.pose_frame=frame or self.frame;self.pose_observed=time.monotonic()-max(0.,age)
                self.pose_source=source;self.uncertainty=uncertainty
            self.pose_error=error;self.revision+=1
    def update_scan(self,packet,age=0.):
        with self.lock:
            self.scan={**packet,'received':time.monotonic()-max(0.,age)};self.revision+=1
    def update_markers(self,packet,age=0.):
        with self.lock:
            self.marker_observations=packet
            self.marker_observed=time.monotonic()-max(0.,age)
            self.revision+=1
    def snapshot(self):
        with self.lock:
            if self.grid is None and self.pose is None and self.scan is None and self.marker_observations is None:return None
            now=time.monotonic();pose_age=now-self.pose_observed if self.pose is not None else None
            marker_age=now-self.marker_observed
            markers=({**self.marker_observations,'age_s':round(marker_age,3)}
                     if self.marker_observations is not None and marker_age<=1.5 else None)
            scan=None if self.scan is None else {k:v for k,v in self.scan.items()if k!='received'}
            if scan is not None:scan['age_s']=round(now-self.scan['received'],3)
            return {'type':'map' if self.grid is not None else 'telemetry','revision':self.revision,
                'map_revision':self.map_revision,'grid':self.grid,'frame':self.frame,
                'session_id':self.session_id,
                'applied_map_sha256':self.applied_map_sha256,'tracking_error':self.tracking_error,
                'pose':self.pose,'pose_frame':self.pose_frame,'pose_source':self.pose_source,
                'pose_age_s':round(pose_age,3) if pose_age is not None else None,
                'pose_live':pose_age is not None and pose_age<=.5,'pose_error':self.pose_error,
                'uncertainty_m':self.uncertainty,'scan':scan,'marker_observations':markers,
                'map_age_seconds':now-self.updated if self.grid is not None else None}


def yaw(q):
    return math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))


def placement_transform(placed,measured):
    angle=math.atan2(math.sin(placed[2]-measured[2]),math.cos(placed[2]-measured[2]))
    c,s=math.cos(angle),math.sin(angle)
    return [placed[0]-c*measured[0]+s*measured[1],placed[1]-s*measured[0]-c*measured[1],angle]


def aligned_grid(grid,transform):
    result=dict(grid)
    x,y,heading=grid['origin'];c,s=math.cos(transform[2]),math.sin(transform[2])
    result['origin']=[transform[0]+c*x-s*y,transform[1]+s*x+c*y,
                      math.atan2(math.sin(heading+transform[2]),math.cos(heading+transform[2]))]
    return result


def project_scan(msg,translation,quaternion,maximum=720):
    x,y,z,w=quaternion
    norm=math.sqrt(x*x+y*y+z*z+w*w)
    if not math.isfinite(norm) or norm<1e-9:raise ValueError('Invalid scan transform')
    x,y,z,w=(value/norm for value in (x,y,z,w))
    r00,r01,r10,r11=1-2*(y*y+z*z),2*(x*y-z*w),2*(x*y+z*w),1-2*(x*x+z*z)
    points=[]
    stride=max(1,math.ceil(len(msg.ranges)/maximum))
    for i in range(0,len(msg.ranges),stride):
        distance=msg.ranges[i]
        if not math.isfinite(distance) or not msg.range_min<=distance<=msg.range_max:continue
        angle=msg.angle_min+i*msg.angle_increment
        px,py=distance*math.cos(angle),distance*math.sin(angle)
        points.append([round(translation[0]+r00*px+r01*py,4),round(translation[1]+r10*px+r11*py,4)])
    return points


def depth_marker_pairs(packet,now):
    """Keep only co-observed calibrated RGB-D positions, never saved map poses."""
    if not isinstance(packet,dict) or packet.get('state')!='Scanning':return None
    observed=packet.get('observed_at')
    if type(observed) not in (float,int) or not math.isfinite(observed) or not -.1<=now-observed<=.75:return None
    found=[]
    for detection in packet.get('detections',[]):
        if not isinstance(detection,dict) or type(detection.get('id')) is not int or not detection.get('registered'):continue
        xyz=detection.get('camera_position_m')
        if (detection.get('depth_samples',0)<=0 or not isinstance(xyz,list) or len(xyz)!=3 or
                any(type(v) not in (float,int) or not math.isfinite(v) for v in xyz)):continue
        found.append({'id':detection['id'],'camera_position_m':xyz,'depth_samples':detection['depth_samples']})
    if len(found)<2:return None
    return {'dictionary':packet.get('dictionary'),'observed_at':observed,'detections':found}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--map-topic',default='/map');parser.add_argument('--map-frame',default='map');parser.add_argument('--base-frame',default='base_link')
    parser.add_argument('--fixture',help='Replay fixture environment.json without ROS for browser verification')
    args=parser.parse_args();source=MappingSource()
    if args.fixture:
        from kenny_rl.environment import validate_environment
        env=validate_environment(json.loads(Path(args.fixture).read_text()))
        source.update_map(env['grid']);source.update_pose([*env['start'],0],source='Fixture preview')
        def replay():
            while True:
                source.update_map(env['grid']);time.sleep(1)
        threading.Thread(target=replay,daemon=True).start()
    else:
        try:
            import rclpy
            from rclpy.node import Node
            from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, qos_profile_sensor_data
            from nav_msgs.msg import OccupancyGrid
            from sensor_msgs.msg import LaserScan
            from geometry_msgs.msg import PoseWithCovarianceStamped, TransformStamped
            from std_msgs.msg import String
            from tf2_ros import Buffer, TransformListener, TransformException, StaticTransformBroadcaster
        except ImportError as e:
            parser.error(f'ROS 2 is unavailable. Source /opt/ros/jazzy/setup.bash first. {e}')
        rclpy.init()
        class Bridge(Node):
            def __init__(self):
                super().__init__('kenny_editor_bridge')
                self.buffer=Buffer();self.listener=TransformListener(self.buffer,self)
                self.latest_scan=None;self.primary_at=-math.inf;self.covariance=None
                self.operator_alignment=None;self.raw_grid=None;self.raw_frame=None;self.pose_broadcaster=None
                self.applied_transform_msg=None
                self.anchor_invalid=False
                self.reference_pub=self.create_publisher(String,'/kenny/editor/placement_reference',10)
                source.apply_callback=self.apply_pose
                qos=QoSProfile(depth=1,reliability=ReliabilityPolicy.RELIABLE,durability=DurabilityPolicy.TRANSIENT_LOCAL)
                self.sub=self.create_subscription(OccupancyGrid,args.map_topic,self.map_callback,qos)
                if args.map_topic!='/map':
                    self.create_subscription(OccupancyGrid,'/map',lambda msg:self.map_callback(msg,True),qos)
                self.create_subscription(LaserScan,'/scan',lambda msg:setattr(self,'latest_scan',msg),qos_profile_sensor_data)
                self.create_subscription(String,'/kenny/aruco/status',self.marker_callback,10)
                self.create_subscription(PoseWithCovarianceStamped,'/pose',self.pose_uncertainty,qos_profile_sensor_data)
                self.create_timer(.2,self.pose_callback)
                self.create_timer(.2,self.scan_callback)
                self.create_timer(.5,self.reference_callback)
            def marker_callback(self,msg):
                try:packet=depth_marker_pairs(json.loads(msg.data),time.time())
                except (ValueError,TypeError):packet=None
                age=time.time()-packet['observed_at'] if packet else 0.
                source.update_markers(packet,age)
            def reference_callback(self):
                import json
                if self.operator_alignment is not None and self.pose_broadcaster is not None and self.applied_transform_msg is not None:
                    self.pose_broadcaster.sendTransform(self.applied_transform_msg)
                self.reference_pub.publish(String(data=json.dumps({'active':self.operator_alignment is not None,
                    'map_sha256':source.applied_map_sha256,'session_id':source.session_id,
                    'source':'operator placement','absolute_accuracy_verified':False})))
            def pose_uncertainty(self,msg):
                covariance=max(msg.pose.covariance[0],msg.pose.covariance[7])
                if math.isfinite(covariance) and covariance>=0:self.covariance=math.sqrt(covariance)
            def map_callback(self,msg,fallback=False):
                if fallback and time.monotonic()-self.primary_at<5:return
                if not fallback and msg.header.frame_id!=args.map_frame:
                    self.get_logger().error('Map frame differs from configured map frame');return
                if msg.info.width*msg.info.height>4_000_000:
                    self.get_logger().error('Map exceeds 4 million cells');return
                p=msg.info.origin.position
                data=[-1 if v<0 else 100 if v>=65 else 0 if v<=19 else -1 for v in msg.data]
                if not fallback:self.primary_at=time.monotonic()
                grid={'width':msg.info.width,'height':msg.info.height,'resolution':msg.info.resolution,'origin':[p.x,p.y,yaw(msg.info.origin.orientation)],'data':data}
                if msg.header.frame_id=='slam_map':self.raw_grid=grid;self.raw_frame=msg.header.frame_id
                if self.operator_alignment is not None and msg.header.frame_id=='slam_map':
                    source.update_map(aligned_grid(grid,self.operator_alignment),'map')
                else:source.update_map(grid,msg.header.frame_id)
            def apply_pose(self,pose,map_sha256):
                if 'kenny_main_controller' in self.get_node_names():
                    raise ValueError('Pause autonomous navigation before applying a manual pose; scan-only SLAM may keep running')
                if self.raw_grid is None or self.raw_frame!='slam_map':
                    raise ValueError('Wait for the live scan-only SLAM map before applying pose')
                try:
                    tf=self.buffer.lookup_transform('slam_map',args.base_frame,rclpy.time.Time())
                except TransformException as error:raise ValueError('Live scan-only SLAM frame required: '+str(error)) from error
                age=self.get_clock().now().nanoseconds/1e9-tf.header.stamp.sec-tf.header.stamp.nanosec/1e9
                if not -.1<=age<=.5:raise ValueError('SLAM pose is stale; wait for fresh measurements')
                p=tf.transform.translation
                transform=placement_transform(pose,[p.x,p.y,yaw(tf.transform.rotation)])
                msg=TransformStamped();msg.header.stamp=self.get_clock().now().to_msg()
                msg.header.frame_id='map';msg.child_frame_id='slam_map'
                msg.transform.translation.x,msg.transform.translation.y=transform[:2]
                msg.transform.rotation.z,msg.transform.rotation.w=math.sin(transform[2]/2),math.cos(transform[2]/2)
                if self.pose_broadcaster is not None:self.destroy_publisher(self.pose_broadcaster.pub_tf)
                self.pose_broadcaster=StaticTransformBroadcaster(self)
                self.pose_broadcaster.sendTransform(msg)
                self.applied_transform_msg=msg
                self.buffer.set_transform_static(msg,'operator placement')
                self.operator_alignment=transform
                with source.lock:
                    source.applied_map_sha256=map_sha256;source.scan=None
                if self.raw_grid is not None:source.update_map(aligned_grid(self.raw_grid,transform),'map')
                source.update_pose(pose,'map',age=age,source='Operator placement + LiDAR SLAM + encoders')
                self.get_logger().info(f'Operator map pose applied: {pose}; map hash {map_sha256}')
                return {'pose':pose,'frame':'map','map_sha256':map_sha256,'session_id':source.session_id}
            def pose_callback(self):
                if self.operator_alignment is not None and (self.anchor_invalid or 'kenny_main_controller' in self.get_node_names()):
                    self.operator_alignment=None
                    if self.pose_broadcaster is not None:
                        self.destroy_publisher(self.pose_broadcaster.pub_tf)
                        self.pose_broadcaster=None
                    with source.lock:
                        source.applied_map_sha256=None
                    self.anchor_invalid=False
                    if self.raw_grid is not None:source.update_map(self.raw_grid,'slam_map')
                    self.get_logger().info('Localization ownership/map changed; operator pose anchor withdrawn')
                frame=source.frame if source.grid is not None else args.map_frame
                try:
                    tf=self.buffer.lookup_transform(frame,args.base_frame,rclpy.time.Time())
                    age=(self.get_clock().now().nanoseconds-(tf.header.stamp.sec*1_000_000_000+tf.header.stamp.nanosec))/1e9
                    if not -.1<=age<=.5:
                        source.update_pose(None,error='Map pose transform is stale');return
                    p=tf.transform.translation;source.update_pose([p.x,p.y,yaw(tf.transform.rotation)],frame,age,
                        source='Operator placement + LiDAR SLAM + encoders' if self.operator_alignment is not None else 'SLAM + wheel encoders',
                        uncertainty=None if self.operator_alignment is not None else self.covariance)
                except TransformException as error:
                    try:
                        tf=self.buffer.lookup_transform('odom',args.base_frame,rclpy.time.Time())
                        age=self.get_clock().now().nanoseconds/1e9-tf.header.stamp.sec-tf.header.stamp.nanosec/1e9
                        if not -.1<=age<=.5:raise TransformException('Odometry transform is stale')
                        p=tf.transform.translation
                        source.update_pose([p.x,p.y,yaw(tf.transform.rotation)],'odom',age,
                            source='Wheel odometry only',error=str(error))
                    except TransformException:source.update_pose(None,error=str(error))
            def scan_callback(self):
                msg=self.latest_scan
                if msg is None:return
                age=self.get_clock().now().nanoseconds/1e9-msg.header.stamp.sec-msg.header.stamp.nanosec/1e9
                if not -.1<=age<=.5:return
                frame=source.frame if source.grid is not None else args.map_frame
                packet={'frame':None,'points':[],'origin':None,'base_points':[],
                    'raw_frame':msg.header.frame_id,'samples':len(msg.ranges),
                    'valid':sum(math.isfinite(v) and msg.range_min<=v<=msg.range_max for v in msg.ranges),
                    'range_max':msg.range_max,'reason':None}
                for target,prefix in ((frame,''),(args.base_frame,'base_')):
                    try:
                        tf=self.buffer.lookup_transform(target,msg.header.frame_id,rclpy.time.Time.from_msg(msg.header.stamp))
                        p,q=tf.transform.translation,tf.transform.rotation
                        packet[prefix+'points']=project_scan(msg,[p.x,p.y,p.z],[q.x,q.y,q.z,q.w])
                        if not prefix:packet.update(frame=frame,origin=[p.x,p.y])
                    except (TransformException,ValueError) as error:
                        if not prefix:packet['reason']=str(error)
                source.update_scan(packet,age)
        node=Bridge();threading.Thread(target=lambda:rclpy.spin(node),daemon=True).start()
        def publish_operator_tracking():
            from backend.cloud_maps import publish_placed_pose
            while rclpy.ok():
                packet=source.snapshot()
                if packet and packet.get('applied_map_sha256') and packet.get('pose_frame')=='map' and packet.get('pose_live'):
                    try:
                        publish_placed_pose(packet)
                        error=None
                    except Exception as issue:
                        error=str(issue)
                        if 'Tracking map changed' in error:node.anchor_invalid=True
                    with source.lock:
                        if source.tracking_error!=error:
                            source.tracking_error=error;source.revision+=1
                time.sleep(1)
        threading.Thread(target=publish_operator_tracking,daemon=True).start()
    try:
        import uvicorn
        from backend.main import app
    except ImportError:
        from backend.server import serve
        serve(args.host,args.port,source)
    else:
        app.state.mapping_source=source;uvicorn.run(app,host=args.host,port=args.port)


if __name__=='__main__':main()
