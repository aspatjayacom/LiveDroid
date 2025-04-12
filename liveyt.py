import subprocess
import os
import time
import threading
import shutil
import sys
from pathlib import Path

class Color:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def get_base_path():
    return Path("/storage/emulated/0/Live")

def monitor_stderr(process, log_file):
    with open(log_file, "w", encoding="utf-8") as log:
        for line in process.stderr:
            if any(keyword in line.lower() for keyword in ["error", "failed", "disconnect", "broken"]):
                log.write(f"[!!] {line}")

def start_stream(video_file, stream_key, stream_url, stream_duration, status_dict, lock):
    base_path = get_base_path()
    logs_dir = base_path
    logs_dir.mkdir(exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"{Path(video_file).stem}_{timestamp}_log.txt"

    video_path = base_path / video_file
    if not video_path.exists():
        print(f"{Color.RED} Video tidak ditemukan: {video_path}{Color.RESET}")
        return

    if shutil.which("ffmpeg") is None:
        print(f"{Color.RED} ffmpeg tidak ditemukan di PATH!{Color.RESET}")
        return

    has_audio = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
        "stream=codec_type", "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path)
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    command = [
        "ffmpeg",
        "-nostdin",
        "-re",
        "-stream_loop", "-1",
        "-i", str(video_path)
    ]

    if not has_audio.stdout.strip():
        command += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

    command += ["-c:v", "copy"]
    command += ["-c:a", "copy"]
    command += ["-threads", "0"]
    command += ["-f", "flv", stream_url]

    nice_level = 5

    try:
        process = subprocess.Popen([
            "nice", f"-n{nice_level}", *command
        ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)

        monitor_thread = threading.Thread(target=monitor_stderr, args=(process, log_file))
        monitor_thread.start()

        def status_updater():
            mins = stream_duration // 60
            while mins > 0:
                with lock:
                    status_dict[video_file] = mins
                with open(log_file, "a", encoding="utf-8") as log:
                    log.write(f"LIVE: {video_file} | Sisa waktu: {mins} menit\n")
                mins -= 1
                time.sleep(60)

        updater_thread = threading.Thread(target=status_updater)
        updater_thread.start()

        updater_thread.join()
        monitor_thread.join()

        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            with open(log_file, "a", encoding="utf-8") as log:
                log.write("[!!] ffmpeg tidak terminate secara normal, dipaksa kill\n")

        if process.returncode != 0:
            stderr_output = process.stderr.read()
            with open(log_file, "a", encoding="utf-8") as log:
                log.write(f"[!!] ffmpeg keluar dengan kode {process.returncode}\n")
                log.write(stderr_output)

        print(f"\n{Color.GREEN} Live Streaming Selesai.{Color.RESET}")

    except Exception as e:
        with open(log_file, "w", encoding="utf-8") as log:
            log.write(f"[!!] Terjadi error: {e}\n")

def read_stream_keys():
    base_path = get_base_path()
    data_file = base_path / "StreamKeyYoutube.txt"
    if not data_file.exists():
        print(f"{Color.RED} File StreamKeyYoutube.txt tidak ditemukan.{Color.RESET}")
        return []
    with open(data_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    pairs = []
    for line in lines:
        if ":" in line:
            video, key = line.strip().split(":", 1)
            pairs.append((video.strip(), key.strip()))
    return pairs

def print_status_realtime(status_dict, lock):
    while True:
        with lock:
            lines = [f"{Color.RED} LIVE: {video} | Sisa waktu: {mins} menit{Color.RESET}" for video, mins in status_dict.items()]
        print("\033c", end="")  # Clear screen ANSI
        print("\n".join(lines), flush=True)
        time.sleep(60)

def main():
    print(f"{Color.RED}{Color.BOLD}")
    print("==============================")
    print("     LIVE YOUTUBE ANDROID")
    print("     by Ananda Chakim")
    print("==============================" + f"{Color.RESET}", flush=True)
    print()

    default_stream_url = "rtmp://a.rtmp.youtube.com/live2"
    stream_list = read_stream_keys()
    if not stream_list:
        return

    try:
        duration_input = input(f"{Color.YELLOW} Masukkan Durasi Live (dalam jam): {Color.RESET}").strip()
        duration = int(float(duration_input) * 3600)
    except ValueError:
        print(f"{Color.YELLOW} Durasi tidak valid, default ke 1 jam{Color.RESET}")
        duration = 3600

    if len(stream_list) == 1:
        video_file, stream_key = stream_list[0]
        full_url = f"{default_stream_url}/{stream_key}"
        confirm = input(f"{Color.YELLOW} Jalankan live streaming sekarang? (Y/N): {Color.RESET}").strip().upper()
        if confirm == "Y":
            status_dict = {}
            lock = threading.Lock()
            threading.Thread(target=print_status_realtime, args=(status_dict, lock), daemon=True).start()
            start_stream(video_file, stream_key, full_url, duration, status_dict, lock)
        else:
            print(f"{Color.RED} Live streaming dibatalkan.{Color.RESET}")
    else:
        confirm = input(f"\n{Color.YELLOW} Jalankan Semua live dari List Stream? (Y/N): {Color.RESET}").strip().upper()
        if confirm != "Y":
            print(f"{Color.RED} Live streaming dibatalkan.{Color.RESET}")
            return

        status_dict = {}
        lock = threading.Lock()
        threading.Thread(target=print_status_realtime, args=(status_dict, lock), daemon=True).start()

        threads = []
        for idx, (video_file, stream_key) in enumerate(stream_list):
            full_url = f"{default_stream_url}/{stream_key}"
            t = threading.Thread(
                target=start_stream,
                args=(video_file, stream_key, full_url, duration, status_dict, lock)
            )
            t.start()
            threads.append(t)
            time.sleep(5)

        for t in threads:
            t.join()

if __name__ == "__main__":
    main()
