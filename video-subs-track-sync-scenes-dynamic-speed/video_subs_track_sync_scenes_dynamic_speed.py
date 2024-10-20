# source - right language wrong timing
# target - wrong language right timing

import argparse
import glob
import imagehash
import math
import os
import platform
import re
import subprocess
import sys
import webbrowser
import pysubs2
from PIL import Image

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common'))
if getattr(sys, 'frozen', False):
    # The application is running in a bundled form created by PyInstaller
    from common.utils import *
else:
    # The application is running in a normal Python environment
    from utils import *

def is_sorted(arr):
    for i in range(len(arr) - 1):
        if arr[i] > arr[i + 1]:
            return False
    return True

def get_duration(video_path):
    print('Getting video duration via ffprobe...')
    duration_cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 \"{video_path}\""
    duration = subprocess.check_output(duration_cmd, shell=True, universal_newlines=True)
    return float(duration)

def get_audio_hz(video_path):
    print('Getting audio hz via ffprobe...')
    hz_cmd = f"ffprobe -v error -select_streams a:0 -show_entries stream=sample_rate -of default=noprint_wrappers=1:nokey=1 \"{video_path}\""
    hz = subprocess.check_output(hz_cmd, shell=True, universal_newlines=True)
    return int(hz)

def get_audio_ext(video_path):
    print('Getting video audio extension via ffprobe...')
    audio_ext_cmd = f"ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of default=noprint_wrappers=1:nokey=1 \"{video_path}\""
    audio_ext = subprocess.check_output(audio_ext_cmd, shell=True, universal_newlines=True)
    return audio_ext.strip()

# Function to run FFmpeg command and capture frame information
def capture_frame_info(video_path, output_folder, frame_diff, video_tbn, video_fps, video_pos_per_frame, ffmpeg_script):
    print('Getting video new scene frame information via ffmpeg...')
    ffmpeg_cmd = (
        f"{ffmpeg_script} -loglevel quiet -i \"{video_path}\" "
        f"-filter_complex \"select='gt(scene,{frame_diff/100})',metadata=print:file={output_folder}/time.txt\" "
        f"-vsync vfr \"{output_folder}/img%05d.jpg\""
    )
    subprocess.run(ffmpeg_cmd, shell=True)

    # Parse time.txt to capture frame information
    frame_info = []
    with open(f"{output_folder}/time.txt", "r") as time_file:
        lines = time_file.readlines()
        for index, line in enumerate(lines):
            match = re.match(r'frame:(\d+)\s+pts:(\d+)\s+pts_time:(\d+.?\d*)', line)
            if match:
                pts = int(match.group(2))
                full_video_index = int(round(pts / video_pos_per_frame))
                scene_frame_index = int(match.group(1))
                frame_index_in_its_second = round(full_video_index % video_fps)

                hash = None
                try:
                    # NOTE: file names start from 1, not 0 like the index
                    img = Image.open('{}/img{:05d}.jpg'.format(output_folder, scene_frame_index + 1))
                    hash = imagehash.average_hash(img)
                except FileNotFoundError as e:
                    pass

                frame_info.append({
                    "scene_frame_index": scene_frame_index,
                    "index": full_video_index,
                    "second_index": frame_index_in_its_second,
                    "pts": pts,
                    "pts_s": pts / video_tbn,
                    "pts_ms": pts / video_tbn * 1000,
                    "pts_time": float(match.group(3)),
                    "hash": hash
                })

    return frame_info

def find_twin_frames(main_frame_infos, brothers_frame_infos, reverse_main_and_twin = False):
    pairs = []
    for main_frame_infos in main_frame_infos:
        current_pair = {'main': main_frame_infos['scene_frame_index'], 'twin': None, 'distance': float('inf') }
        for brothers_frame_info in brothers_frame_infos:
            hamming_distance = main_frame_infos['hash'] - brothers_frame_info['hash']
            if hamming_distance < current_pair['distance']:
                current_pair['distance'] = hamming_distance
                current_pair['twin'] = brothers_frame_info['scene_frame_index']
        pairs.append(current_pair)

    # remove bad twins
    # - twin appearing multiple times
    # - twin not in order
    double_twin_indexes = {}
    bad_indexes = []

    # bad side AFTER the reversing
    # the "bad" side is always the one with the most frames
    # if it is the source it will be main (because AFTER reversal it is main)
    # if it is the target it will be twin (because AFTER reversal it is twin)
    possibly_bad_side = 'main' if reverse_main_and_twin else 'twin'
    
    for index, pair in enumerate(pairs):
        # if requested to use twin as main
        if reverse_main_and_twin:
            print('reversing', pair['twin'], 'and replacing it with', pair['main'])
            print(pair)
            temp_twin = pair['twin']
            pair['twin'] = pair['main']
            pair['main'] = temp_twin
        
        # count frame appearance (will use it to find double appearance)
        if pair[possibly_bad_side] not in double_twin_indexes:
            double_twin_indexes[pair[possibly_bad_side]] = []
        double_twin_indexes[pair[possibly_bad_side]].append(index)
   
    # remove twin appearing multiple times
    for value in double_twin_indexes.values():
        if len(value) > 1:
            print(f"Same frame indexes: {value}")
            bad_indexes += value
        
    for bad_index in sorted(bad_indexes, reverse=True):
        pairs.pop(bad_index)

    # NOTE this only works with 1 frame error groups, but I've never found bigger groups in my tests
    bad_indexes = []
    for index, pair in enumerate(pairs):
        # a frame cannot have a lower index than the previous one
        if index > 0 and pair[possibly_bad_side] < pairs[index - 1][possibly_bad_side]:
            bad_indexes.append(index)
        # a frame cannot have a higher index than the next one
        if index < len(pairs) - 1 and pair[possibly_bad_side] > pairs[index + 1][possibly_bad_side]:
            bad_indexes.append(index)
    
    for bad_index in sorted(bad_indexes, reverse=True):
        pairs.pop(bad_index)

    pairs_twin_indexes = [pair[possibly_bad_side] for pair in pairs if pair[possibly_bad_side] in pairs]
    if not is_sorted(pairs_twin_indexes):
        print('Found a case unhandled by the software: too much unordered groups of frames')
        sys.exit(1)

    return pairs

def frame_index_to_timecodes(pairs, source_frame_infos, target_frame_infos, source_fps, taget_fps):
    timecodes = []
    for pair in pairs:
        current_source_frame = source_frame_infos[pair['main']]
        matching_target_frame = target_frame_infos[pair['twin']]

        # [MS SOURCE, MS TARGET] pair:
        # first of the pair
        # current_source_frame['pts_ms']
        # second of the pair
        # matching_target_frame['pts_ms']
        timecodes.append([current_source_frame['pts_ms'], matching_target_frame['pts_ms']])

    return timecodes

def find_bounds_and_interpolate(pairs, ms):
    lower_pair = None
    upper_pair = None

    for pair in pairs:
        if pair[0] <= ms:
            lower_pair = pair
        else:
            upper_pair = pair
            break

    if not lower_pair or not upper_pair:
        return None

    # Calculate the interpolated target time
    time_diff_ratio = (ms - lower_pair[0]) / (upper_pair[0] - lower_pair[0])
    target_time = lower_pair[1] + time_diff_ratio * (upper_pair[1] - lower_pair[1])

    return target_time

def process_subtitles(input_file, output_file, pairs):
    subs = pysubs2.load(input_file)

    for line in subs:
        # Get the start and end time in milliseconds
        start_ms = line.start
        end_ms = line.end

        # Interpolate new timings
        new_start_ms = find_bounds_and_interpolate(pairs, start_ms)
        new_end_ms = find_bounds_and_interpolate(pairs, end_ms)

        if new_start_ms is not None:
            line.start = int(new_start_ms)
        if new_end_ms is not None:
            line.end = int(new_end_ms)

    # Save the modified subtitle file
    subs.save(output_file)

    return output_file

def describe_frame_infos(frame_dict):
    description = {
        'scene_frame_index': f"Scene Frame Index: {frame_dict['scene_frame_index']}",
        'index': f"Index: {frame_dict['index']}",
        'second_index': f"Index inside second: {frame_dict['second_index']}",
        'pts': f"PTS (Timestamp): {frame_dict['pts']}",
        'pts_s': f"PTS (Seconds): {frame_dict['pts_s']:.4f}",
        'pts_ms': f"PTS (Milliseconds): {frame_dict['pts_ms']:.1f}",
        'pts_time': f"PTS (Time): {frame_dict['pts_time']:.4f}",
        'hash': f"Hash String: {str(frame_dict['hash'])}"
    }

    for key, value in description.items():
        print(value)
    print("----------------------------------")

parser = argparse.ArgumentParser(description='Adjusts audio duration based on 2 safe frame pairs of videos')

parser.add_argument("-sp", "--source-path", help="video with wrong timing", default="INPUT")
parser.add_argument("-tp", "--target-path", help="video with right timing", default="INPUT")
parser.add_argument("-ssp", "--source-sub-path", help="sub with wrong timing", default="INPUT")
parser.add_argument("-fdp", "--frame-diff-percentage", help="difference between frames to start a new scene", type=int, default=30)

parser.add_argument("-ff",  "--ffmpeg", help="ffmpeg binary path", default='ffmpeg')

ARGS = parser.parse_args()

ffmpeg_script = ARGS.ffmpeg

source_path = ARGS.source_path
target_path = ARGS.target_path
source_sub_path = ARGS.source_sub_path
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

source_video_folder = os.path.dirname(source_path)

# Create output folders if they don't exist
os.makedirs(source_frames_folder, exist_ok=True)
os.makedirs(target_frames_folder, exist_ok=True)

# Clean frame directories
delete_frame_cache_files(source_frames_folder)
delete_frame_cache_files(target_frames_folder)

# Get FPS and TBN for the source video
source_fps = get_fps(source_path)
source_tbn = get_tbn(source_path)
source_pos_per_frame = source_tbn / source_fps
source_duration = get_duration(source_path)

print('source_duration', source_duration)

# Get FPS and TBN for the target video
target_fps = get_fps(target_path)
target_tbn = get_tbn(target_path)
target_pos_per_frame = target_tbn / target_fps
target_duration = get_duration(target_path)

# Print the FPS and TBN for both videos
print('')
print(f"Source video - FPS: {source_fps}, TBN: {source_tbn}, PPF: {source_pos_per_frame}")
print(f"Target video - FPS: {target_fps}, TBN: {target_tbn}, PPF: {target_pos_per_frame}", end="\n\n")

# Run FFmpeg commands and capture frame information for both videos
open_folder(source_frames_folder)
source_frame_info = capture_frame_info(
    video_path=source_path,
    output_folder=source_frames_folder,
    frame_diff=frame_diff_percentage,
    video_tbn=source_tbn,
    video_fps=source_fps,
    video_pos_per_frame=source_pos_per_frame,
    ffmpeg_script=ffmpeg_script
)
open_folder(target_frames_folder)
target_frame_info = capture_frame_info(
    video_path=target_path,
    output_folder=target_frames_folder,
    frame_diff=frame_diff_percentage,
    video_tbn=target_tbn,
    video_fps=target_fps,
    video_pos_per_frame=target_pos_per_frame,
    ffmpeg_script=ffmpeg_script
)

print('')
# Prompt the user to input the start frame index for the source video
source_start_frame = input("Check the {0} directory and enter the start frame number for the source video: ".format(source_frames_folder))
# Prompt the user to input the start frame index for the target video
target_start_frame = input("Check the {0} directory and enter the start frame number for the target video: ".format(target_frames_folder))

# Convert the input values to integers
source_start_frame = int(source_start_frame) - 1
target_start_frame = int(target_start_frame) - 1

print("Source video safe start frame infos:")
describe_frame_infos(source_frame_info[source_start_frame])
print("Target video safe start frame infos:")
describe_frame_infos(target_frame_info[target_start_frame])
print("Hamming distance between frames:")
print(target_frame_info[target_start_frame]['hash'] - source_frame_info[source_start_frame]['hash'])
print("\n")

# Prompt the user to input the end frame index for the source video
source_end_frame = input("Enter the end frame index for the source video: ")
# Prompt the user to input the end frame index for the target video
target_end_frame = input("Enter the end frame index for the target video: ")

# Convert the input values to integers
source_end_frame = int(source_end_frame) - 1
target_end_frame = int(target_end_frame) - 1

print("Source video safe end frame infos:")
describe_frame_infos(source_frame_info[source_end_frame])
print("Target video safe end frame infos:")
describe_frame_infos(target_frame_info[target_end_frame])
print("Hamming distance between frames:")
print(target_frame_info[target_end_frame]['hash'] - source_frame_info[source_end_frame]['hash'])
print("\n")

if source_frame_info[source_end_frame]["scene_frame_index"] != source_end_frame or target_frame_info[target_end_frame]["scene_frame_index"] != target_end_frame:
    print("SOMETHING IS WRONG WITH FRAME INDEXES!")
    sys.exit(1)

# Find twin frames
twins = None
if target_end_frame - target_start_frame < source_end_frame - source_start_frame:
    twins = find_twin_frames(target_frame_info[target_start_frame:target_end_frame + 1], source_frame_info[source_start_frame:source_end_frame + 1], reverse_main_and_twin=True)
else:
    twins = find_twin_frames(source_frame_info[source_start_frame:source_end_frame + 1], target_frame_info[target_start_frame:target_end_frame + 1], reverse_main_and_twin=False)

# Re-add manual inserted twins
if twins[0]['main'] > source_start_frame: # if it was removed as a duplicate, re-add the manually provided safe start
    twins.insert(0, {'main': source_start_frame, 'twin': target_start_frame, 'distance': 0})
if twins[-1]['main'] < source_end_frame: # if it was removed as a duplicate, re-add the manually provided safe end
    twins.append({'main': source_end_frame, 'twin': target_end_frame, 'distance': 0})

# Timecodes
timecodes = frame_index_to_timecodes(twins, source_frame_info, target_frame_info, source_fps, target_fps)

# Build html to show pairs in the browser
with open('test.html', 'w'):
    pass
with open('test.html', "a") as pair_preview_file:
    for pair_index, pair in enumerate(twins):
        old_time = timecodes[pair_index][0]
        new_time = timecodes[pair_index][-1]
        old_time_string = "{:02d}:{:02d}:{:02d}".format(int(math.floor(old_time / 3600)), int(math.floor(old_time / 60)), int(old_time % 60))
        new_time_string = "{:02d}:{:02d}:{:02d}".format(int(math.floor(new_time / 3600)), int(math.floor(new_time / 60)), int(new_time % 60))

        pair_preview_file.write('''
        <div style="min-height: 450px;">
            <h1>Association index {pair_index}</h1>
            <img src="{source_frames_folder}/img{source_index:05d}.jpg" loading="lazy" style="width: 48%;">
            <img src="{target_frames_folder}/img{target_index:05d}.jpg" loading="lazy" style="width: 48%;">
            <p>{old_frame_index}frame {old_sample}sample ({old_time}) --> {new_sample}sample ({new_time})</p>
        </div>
        '''.format(
            pair_index=pair_index,
            source_frames_folder=source_frames_folder,
            target_frames_folder=target_frames_folder,
            source_index=pair['main'] + 1,
            target_index=pair['twin'] + 1,
            old_frame_index=source_frame_info[pair['main']]['index'],
            old_sample=timecodes[pair_index][0],
            new_sample=timecodes[pair_index][-1],
            old_time=old_time_string,
            new_time=new_time_string
        ))

# Open the html
webbrowser.open('file://' + os.path.realpath('test.html'))

# Manually remove bad indexes
removing_twins = input("If you want to manually remove twins, write their index separated by comma (ex: '5,20'):\n")
removing_indexes = removing_twins.split(',')
int_numbers = []
for num in removing_indexes:
    try:
        int_value = int(num)
        int_numbers.append(int_value)
    except ValueError:
        pass
sorted_numbers = sorted(int_numbers, reverse=True)
for index in sorted_numbers:
    print("Removing the pair with index {}".format(index))
    twins.pop(index)
    timecodes.pop(index)

# Initial timecode to cut off the beginning
new_start_timecode = timecodes[0][0] - timecodes[0][1]
timecodes.insert(0, [new_start_timecode, 1])

# Final timecode to keep the speed of the last safe segment until the end
timecodes_last_index = len(timecodes) - 1
last_safe_speed = (timecodes[timecodes_last_index][1] - timecodes[timecodes_last_index - 1][1]) / (timecodes[timecodes_last_index][0] - timecodes[timecodes_last_index - 1][0])
source_end = source_duration * 1000 # sec to ms
new_end = ((source_end - timecodes[timecodes_last_index][0]) * last_safe_speed) + timecodes[timecodes_last_index][1]
timecodes.append([source_end - 1, new_end - 1])

# Generate subtitles, force them to be srt
output_sub_path = process_subtitles(source_sub_path, source_sub_path + '.srt', timecodes)

# Open folder with results
open_folder(os.path.dirname(output_sub_path))
print('The output file name is {output_sub_name}'.format(output_sub_name=os.path.basename(output_sub_path)))

# Clean frame directories?
clean_frame_dir = input("Do you want to clean frame directories? [Y/N]: ")

if clean_frame_dir.lower() == 'y':
    delete_frame_cache_files(source_frames_folder)
    delete_frame_cache_files(target_frames_folder)