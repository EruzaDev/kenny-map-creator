"""Use SLAM Toolbox's official launch to handle Jazzy lifecycle transitions."""
from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    root=Path(__file__).resolve().parent
    official=Path(get_package_share_directory('slam_toolbox'))/'launch/online_async_launch.py'
    return LaunchDescription([
        DeclareLaunchArgument('host',default_value='0.0.0.0'),
        DeclareLaunchArgument('port',default_value='8000'),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(str(official)),launch_arguments={
            'slam_params_file':str(root/'slam.yaml'),
            'use_sim_time':'false','autostart':'true','use_lifecycle_manager':'false',
        }.items()),
        ExecuteProcess(cmd=['python3',str(root/'bridge.py'),'--host',LaunchConfiguration('host'),'--port',LaunchConfiguration('port')],output='screen'),
    ])
