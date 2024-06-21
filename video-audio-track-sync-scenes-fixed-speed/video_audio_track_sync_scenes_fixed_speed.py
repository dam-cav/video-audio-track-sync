# source - right language wrong timing
# target - wrong language right timing

import argparse
import re
import os
import subprocess
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common'))
if getattr(sys, 'frozen', False):
    # The application is running in a bundled form created by PyInstaller
    from common.utils import *
else:
    # The application is running in a normal Python environment
    from utils import *

# Function to run FFmpeg command and capture frame information
def capture_frame_info(video_path, output_folder, frame_diff, video_tbn, video_fps, video_pos_per_frame, edges_frame_search_minutes, ffmpeg_script):
    print('Getting video new scene frame information via ffmpeg...')
    # check just first and last edges_frame_search_minutes min (ex: 60 * 15 min = 900 seconds)
    search_range = edges_frame_search_minutes * 60
    ffmpeg_cmd = (
        f"{ffmpeg_script} -loglevel quiet -ss 0 -i \"{video_path}\" -t {search_range} "
        f"-filter_complex \"select='gt(scene,{frame_diff/100})',metadata=print:file={output_folder}/start_time.txt\" "
        f"-vsync vfr \"{output_folder}/img%03d.jpg\""
    )
    subprocess.run(ffmpeg_cmd, shell=True)

    matches = []
    with open(f"{output_folder}/start_time.txt", "r") as time_file:
        lines = time_file.readlines()
        for index, line in enumerate(lines):
            match = re.match(r'frame:(\d+)\s+pts:(\d+)\s+pts_time:(\d+.?\d*)', line)
            if match:
                matches.append(match)

    duration_cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 \"{video_path}\""
    duration = float(subprocess.check_output(duration_cmd, shell=True, universal_newlines=True))

    approx_total_frames = duration * video_fps
    start_of_end = round(approx_total_frames - (search_range * video_fps))

    start_matches_len = len(matches)
    ss_end_frame_search = duration - search_range
    ffmpeg_cmd = (
        f"{ffmpeg_script} -loglevel quiet -ss {ss_end_frame_search} -i \"{video_path}\" -t {search_range} "
        f"-filter_complex \"select='gt(scene,{frame_diff/100})',metadata=print:file={output_folder}/end_time.txt\" "
        f"-vsync vfr -start_number {len(matches)} \"{output_folder}/img%03d.jpg\""
    )
    print(ffmpeg_cmd) 
    subprocess.run(ffmpeg_cmd, shell=True)

    # Parse time.txt to capture frame information
    frame_info = []
    with open(f"{output_folder}/end_time.txt", "r") as time_file:
        lines = time_file.readlines()
        for index, line in enumerate(lines):
            match = re.match(r'frame:(\d+)\s+pts:(\d+)\s+pts_time:(\d+.?\d*)', line)
            if match:
                # + ss_end_frame_search * video_tbn
                # + ss_end_frame_search
                matches.append(match)

    for index, match in enumerate(matches):
        pts = int(match.group(2))
        if index >= start_matches_len:
            pts += round(ss_end_frame_search * video_tbn)
        full_video_index = int(round(pts / video_pos_per_frame))
        frame_info.append({
            "scene_frame_index": int(match.group(1)),
            "index": full_video_index,
            "second_index": round(full_video_index % video_fps),
            "pts": pts,
            "pts_s": pts / video_tbn,
            "pts_ms": pts / video_tbn * 1000,
            "pts_time": float(match.group(3)) if index < start_matches_len else float(match.group(3)) + ss_end_frame_search
        })

    return frame_info

parser = argparse.ArgumentParser(description='Adjusts audio duration based on 2 safe frame pairs of videos')

parser.add_argument("-sp", "--source-path", help="viddeo with wrong timing", default="INPUT")
parser.add_argument("-tp", "--target-path", help="video with right timing", default="INPUT")
parser.add_argument("-efsm", "--edges-frame-search-minutes", help="number of minutes at the beginning and end of videos to search for scene changes", type=int, default=15)
parser.add_argument("-fdp", "--frame-diff-percentage", help="difference between frames to start a new scene", type=int, default=30)

parser.add_argument("-ff",  "--ffmpeg", help="ffmpeg binary path", default='ffmpeg')

ARGS = parser.parse_args()

ffmpeg_script = ARGS.ffmpeg

source_path = ARGS.source_path
target_path = ARGS.target_path
edges_frame_search_minutes = ARGS.edges_frame_search_minutes
frame_diff_percentage = ARGS.frame_diff_percentage

# Check if source_path and target_path are valid video files
if not os.path.isfile(source_path):
    print(f"The source video file '{source_path}' does not exist.")
    sys.exit(1)

if not os.path.isfile(target_path):
    print(f"The target video file '{target_path}' does not exist.")
    sys.exit(1)

# Define output folders for source and target frames
source_frames_folder = "SOURCE_FRAMES"
target_frames_folder = "TARGET_FRAMES"

# Create output folders if they don't exist
os.makedirs(source_frames_folder, exist_ok=True)
os.makedirs(target_frames_folder, exist_ok=True)

# Get FPS and TBN for the source video
source_fps = get_fps(source_path)
source_tbn = get_tbn(source_path)
source_pos_per_frame = source_tbn / source_fps
source_audio_hz = get_audio_hz(source_path)

# Get FPS and TBN for the target video
target_fps = get_fps(target_path)
target_tbn = get_tbn(target_path)
target_pos_per_frame = int(round(target_tbn / target_fps))

# Print the FPS and TBN for both videos
print('')
print(f"Source video - FPS: {source_fps}, TBN: {source_tbn}, PPF: {source_pos_per_frame}")
print(f"Target video - FPS: {target_fps}, TBN: {target_tbn}, PPF: {target_pos_per_frame}", end="\n\n")

# Run FFmpeg commands and capture frame information for both videos
source_frame_info = capture_frame_info(
    video_path=source_path,
    output_folder=source_frames_folder,
    frame_diff=frame_diff_percentage,
    video_tbn=source_tbn,
    video_fps=source_fps,
    video_pos_per_frame=source_pos_per_frame,
    edges_frame_search_minutes=edges_frame_search_minutes,
    ffmpeg_script=ffmpeg_script
)
target_frame_info = capture_frame_info(
    video_path=target_path,
    output_folder=target_frames_folder,
    frame_diff=frame_diff_percentage,
    video_tbn=target_tbn,
    video_fps=target_fps,
    video_pos_per_frame=target_pos_per_frame,
    edges_frame_search_minutes=edges_frame_search_minutes,
    ffmpeg_script=ffmpeg_script
)

open_folder(source_frames_folder)
open_folder(target_frames_folder)

print('')
# Prompt the user to input the start frame index for the source video
source_start_frame = input("Check the {0} directory and enter the start frame number for the source video: ".format(source_frames_folder))
# Prompt the user to input the start frame index for the target video
target_start_frame = input("Check the {0} directory and enter the start frame number for the target video: ".format(target_frames_folder))
print("\n")

# Convert the input values to integers
source_start_frame = int(source_start_frame) - 1
target_start_frame = int(target_start_frame) - 1

print("Source video safe start frame info:")
print(source_frame_info[source_start_frame])
print("Target video safe start frame info:")
print(target_frame_info[target_start_frame])
print("\n")

# Prompt the user to input the end frame index for the source video
source_end_frame = input("Enter the end frame index for the source video: ")
# Prompt the user to input the end frame index for the target video
target_end_frame = input("Enter the end frame index for the target video: ")
print("\n")

# Convert the input values to integers
source_end_frame = int(source_end_frame)
target_end_frame = int(target_end_frame)

print("Source video safe end frame info:")
print(source_frame_info[source_end_frame])
print("Target video safe end frame info:")
print(target_frame_info[target_end_frame])
print("\n")

# Clean frame directories
delete_frame_cache_files(source_frames_folder)
delete_frame_cache_files(target_frames_folder)

# Calculate speed delta
source_safe_duration_ms = (source_frame_info[source_end_frame]["pts"] - source_frame_info[source_start_frame]["pts"]) * 1000 / source_tbn 
target_safe_duration_ms = (target_frame_info[target_end_frame]["pts"] - target_frame_info[target_start_frame]["pts"]) * 1000 / target_tbn

speed_delta = source_safe_duration_ms / target_safe_duration_ms

# Calculate start delta
retimed_start =  source_frame_info[source_start_frame]["pts_ms"] * speed_delta
start_delta = (target_frame_info[target_start_frame]["pts_ms"] - (retimed_start))

# Print commands to run and run them
print("I'm going to run this command, but you can copy-paste it to run it yourself:", end="\n\n")

output_audio_ext = 'opus'
OPUS_WORKAROUND = ", aformat=channel_layouts=7.1|5.1|stereo"

if start_delta > 0:
    ffmpeg_delta_positive_command = (
        '{ffmpeg} -i \"{source_path}\" -filter_complex '
        '"[0:a]rubberband=tempo={speed_delta}{opus_workaround}[a1]; '
        ' [a1]adelay={start_delta}|{start_delta}[aout]" -map "[aout]" -ar {source_audio_hz} -c:a libopus \"{output_name}_synced.{output_audio_ext}\"'
    ).format(
        ffmpeg = ffmpeg_script,
        source_path = source_path,
        speed_delta = speed_delta,
        opus_workaround = OPUS_WORKAROUND,
        start_delta = start_delta,
        output_name = os.path.splitext(target_path)[0],
        output_audio_ext = output_audio_ext
    )

    print(ffmpeg_delta_positive_command, end="\n\n")

    subprocess.run(ffmpeg_delta_positive_command, shell=True)
else:
    ffmpeg_delta_negative_command = (
        '{ffmpeg} -i \"{source_path}\" -filter_complex '
        '"[0:a]rubberband=tempo={speed_delta}{opus_workaround}[a1]" -map "[a1]" -ss {start_delta}ms -ar {source_audio_hz} -c:a libopus \"{output_name}_synced.{output_audio_ext}\"'
    ).format(
        ffmpeg = ffmpeg_script,
        source_path = source_path,
        speed_delta = speed_delta, 
        opus_workaround = OPUS_WORKAROUND,
        start_delta = start_delta,
        output_name = os.path.splitext(target_path)[0],
        output_audio_ext = output_audio_ext
    )

    print(ffmpeg_delta_negative_command, end="\n\n")

    subprocess.run(ffmpeg_delta_negative_command, shell=True)

open_folder(os.path.dirname(target_path))