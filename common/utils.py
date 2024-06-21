import subprocess
import platform
import os

def open_folder(path):
    if platform.system() == 'Windows':
        subprocess.Popen(['explorer', path])
    elif platform.system() == 'Linux':
        # Adjust this line for the file manager in your Linux distribution.
        subprocess.Popen(['xdg-open', path])
    else:
        print("Unsupported operating system")

def delete_frame_cache_files(directory_path):
    # List all files in the directory
    files = os.listdir(directory_path)

    # Iterate through the files and delete JPG files
    for file in files:
        if file.startswith("img") and file.endswith(".jpg") or file == "time.txt":
            file_path = os.path.join(directory_path, file)
            os.remove(file_path)

def get_fps(video_path):
    print('Getting video fps via ffprobe...')
    fps_cmd = f"ffprobe -loglevel quiet -v error -select_streams v:0 -of default=noprint_wrappers=1:nokey=1 -show_entries stream=r_frame_rate \"{video_path}\""
    fps = subprocess.check_output(fps_cmd, shell=True, universal_newlines=True)
    fps_numerator = fps.strip().split('/')[0]
    fps_denominator = fps.strip().split('/')[1]
    return round(float(fps_numerator) / float(fps_denominator), 3)

def get_tbn(video_path):
    print('Getting video tbn via ffprobe...')
    tbn_cmd = f"ffprobe -loglevel quiet -v error -select_streams v:0 -of default=noprint_wrappers=1:nokey=1 -show_entries stream=time_base \"{video_path}\""
    tbn = subprocess.check_output(tbn_cmd, shell=True, universal_newlines=True)
    tbn_int_string = tbn.strip().split('/')[1]
    return int(tbn_int_string)
