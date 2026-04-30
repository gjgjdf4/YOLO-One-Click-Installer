# -*- coding: utf-8 -*-
# ============================================================
# Windows + 完整 Anaconda + YOLO 工程部署脚本 V3
# ============================================================
# V2 改进点：
# 1. 新增统一硬件依赖组 HARDWARE_PACKAGES：pyserial + pyrealsense2
# 2. requirements_yolo.txt 同步记录硬件依赖
# 3. Anaconda 安装包优先从清华 TUNA 镜像下载
# 4. 大文件下载加入 3 次重试
# 5. 弃用 conda run，改为直接调用 conda 环境内部 python.exe
# 6. 对 Anaconda 安装路径和项目路径进行中文/空格强校验
# 7. pip install 增加 --default-timeout=1000，降低大 wheel 下载超时概率
# 8. subprocess 输出解码增加 encoding='utf-8' 和 errors='replace'，防止 Emoji/特殊字符导致崩溃
# 9. test_realsense.py 增加固件匹配和 RealSense Viewer 校验提醒
#
# 运行：
#     python yolo_anaconda_full_deployer_v3.py
# ============================================================

import os
import re
import sys
import json
import time
import shutil
import ctypes
import platform
import subprocess
import urllib.request
from pathlib import Path
from datetime import datetime

CONDA_ENV_NAME = "yolo"
CONDA_PYTHON_VERSION = "3.10"

PROJECT_NAME = "YOLO_Anaconda_Deploy"
DEFAULT_ANACONDA_DIR = r"C:\Users\Public\Anaconda3_YOLO"
DEFAULT_PROJECT_DIR = r"C:\Users\Public\YOLO_Anaconda_Deploy"

TUNA_ANACONDA_ARCHIVE_URL = "https://mirrors.tuna.tsinghua.edu.cn/anaconda/archive/"
OFFICIAL_ANACONDA_ARCHIVE_URL = "https://repo.anaconda.com/archive/"
ANACONDA_FALLBACK_FILE = "Anaconda3-2025.12-2-Windows-x86_64.exe"

DOWNLOAD_RETRIES = 3
DOWNLOAD_RETRY_SLEEP = 5
DOWNLOAD_TIMEOUT = 30

TORCH_PACKAGES = ["torch", "torchvision", "torchaudio"]

TORCH_INDEX = {
    "cpu": "https://download.pytorch.org/whl/cpu",
    "cu118": "https://download.pytorch.org/whl/cu118",
    "cu126": "https://download.pytorch.org/whl/cu126",
    "cu128": "https://download.pytorch.org/whl/cu128",
}

BASIC_PACKAGES = [
    "ultralytics",
    "opencv-python",
    "numpy",
    "pillow",
    "matplotlib",
    "pandas",
    "scipy",
    "tqdm",
    "pyyaml",
    "requests",
    "psutil",
]

EXPORT_PACKAGES = [
    "onnx",
    "onnxruntime",
    "onnxsim",
]

# 统一硬件驱动依赖组：后续要加雷达、机械臂 SDK，也统一放这里
HARDWARE_PACKAGES = [
    "pyserial",
    "pyrealsense2",
]

YOLO_MODEL_MENU = {
    "1": ("YOLOv8n  轻量，速度最快，CPU/GPU 都适合测试", "yolov8n.pt"),
    "2": ("YOLOv8s  小模型，精度比 n 高", "yolov8s.pt"),
    "3": ("YOLOv8m  中等模型，建议有显卡", "yolov8m.pt"),
    "4": ("YOLOv8l  大模型，显存要求高", "yolov8l.pt"),
    "5": ("YOLOv8x  最大模型，显存要求最高", "yolov8x.pt"),
    "6": ("YOLOv9c  YOLOv9 常用检测模型", "yolov9c.pt"),
    "7": ("YOLOv10n YOLOv10 轻量模型", "yolov10n.pt"),
    "8": ("YOLOv10s YOLOv10 小模型", "yolov10s.pt"),
    "9": ("YOLO11n  推荐，轻量稳定", "yolo11n.pt"),
    "10": ("YOLO11s 推荐，速度和精度均衡", "yolo11s.pt"),
    "11": ("YOLO11m 中等模型，建议有显卡", "yolo11m.pt"),
    "12": ("自定义模型路径，例如 best.pt", "CUSTOM"),
}


def print_title(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def print_step(text):
    print("\n[步骤] " + text)


def which(name):
    return shutil.which(name)


def is_windows():
    return platform.system().lower() == "windows"


def is_admin():
    if not is_windows():
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_cmd(cmd, check=True, capture=False, cwd=None):
    if isinstance(cmd, list):
        show = " ".join(str(x) for x in cmd)
        shell = False
    else:
        show = str(cmd)
        shell = True

    print("\n>> " + show)

    if capture:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            shell=shell,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if result.stdout:
            print(result.stdout)
        if check and result.returncode != 0:
            raise RuntimeError("命令执行失败：" + show)
        return result.stdout or ""

    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        shell=shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        universal_newlines=True,
    )

    if process.stdout:
        for line in process.stdout:
            print(line, end="")

    code = process.wait()
    if check and code != 0:
        raise RuntimeError("命令执行失败，返回码 {}：{}".format(code, show))
    return ""


def get_python_info():
    return {
        "executable": sys.executable,
        "version": platform.python_version(),
        "bits": platform.architecture()[0],
        "major": sys.version_info.major,
        "minor": sys.version_info.minor,
    }


def ensure_launcher_python_ok():
    info = get_python_info()
    if info["major"] != 3 or info["minor"] < 8:
        raise RuntimeError("当前 Python 版本过低。请用 Python 3.8 或以上运行本部署脚本。")
    if info["bits"] != "64bit":
        raise RuntimeError("当前 Python 不是 64 位。请安装 64 位 Python。")
    return info


def get_disk_free_gb(path):
    usage = shutil.disk_usage(str(path))
    return usage.free / (1024 ** 3)


def get_memory_gb():
    try:
        import psutil
        return psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        try:
            out = run_cmd(["wmic", "computersystem", "get", "TotalPhysicalMemory"], capture=True, check=False)
            nums = re.findall(r"\d+", out)
            if nums:
                return int(nums[-1]) / (1024 ** 3)
        except Exception:
            pass
    return None


def get_cpu_info():
    return platform.processor() or platform.machine(), os.cpu_count()


def parse_cuda_from_nvidia_smi(text):
    m = re.search(r"CUDA Version:\s*([0-9]+(?:\.[0-9]+)?)", text)
    return m.group(1) if m else None


def get_nvidia_info():
    if not which("nvidia-smi"):
        return {
            "available": False,
            "reason": "未找到 nvidia-smi，可能没有 NVIDIA 显卡或驱动未安装。",
            "cuda_driver": None,
            "gpus": [],
            "raw": "",
        }

    raw = run_cmd(["nvidia-smi"], capture=True, check=False)
    cuda_driver = parse_cuda_from_nvidia_smi(raw)

    gpus = []
    query = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader",
    ]
    query_out = run_cmd(query, capture=True, check=False)
    for line in query_out.splitlines():
        parts = [x.strip() for x in line.split(",")]
        if len(parts) >= 3:
            gpus.append({
                "name": parts[0],
                "memory": parts[1],
                "driver": parts[2],
            })

    return {
        "available": True,
        "reason": "",
        "cuda_driver": cuda_driver,
        "gpus": gpus,
        "raw": raw,
    }


def get_nvcc_version():
    if not which("nvcc"):
        return None
    out = run_cmd(["nvcc", "--version"], capture=True, check=False)
    m = re.search(r"release\s+([0-9]+(?:\.[0-9]+)?)", out)
    return m.group(1) if m else "已安装，但未解析出版本"


def has_non_ascii(path_text):
    try:
        path_text.encode("ascii")
        return False
    except UnicodeEncodeError:
        return True


def has_space(path_text):
    return any(ch.isspace() for ch in path_text)


def assert_clean_path(path, name):
    path_text = str(path)
    bad = []
    if has_non_ascii(path_text):
        bad.append("包含中文或非 ASCII 字符")
    if has_space(path_text):
        bad.append("包含空格")

    if bad:
        raise RuntimeError(
            "{} 不符合工程部署要求：{}\n"
            "当前路径：{}\n"
            "请使用纯英文、无空格路径，例如：\n"
            "  C:\\Users\\Public\\Anaconda3_YOLO\n"
            "  C:\\Users\\Public\\YOLO_Anaconda_Deploy".format(name, "、".join(bad), path_text)
        )


def choose_clean_dir(title, default_dir):
    print_title(title)
    print("要求：路径必须纯英文、无空格。")
    print("默认目录：" + str(default_dir))

    while True:
        s = input("直接回车使用默认目录，或输入目录：\n> ").strip().strip('"')
        p = Path(s) if s else Path(default_dir)
        p = p.resolve()
        try:
            assert_clean_path(p, title)
            return p
        except RuntimeError as e:
            print("\n" + str(e))
            print("请重新输入。")


def urlopen_text_with_retry(url):
    last_error = None
    for i in range(1, DOWNLOAD_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            last_error = e
            print("读取网页失败，第 {}/{} 次：{}".format(i, DOWNLOAD_RETRIES, e))
            if i < DOWNLOAD_RETRIES:
                time.sleep(DOWNLOAD_RETRY_SLEEP)
    raise RuntimeError("读取网页失败：" + str(last_error))


def parse_anaconda_windows_installers(html):
    pattern = r'Anaconda3-[0-9]{4}\.[0-9]{2}-[0-9]+-Windows-x86_64\.exe'
    names = sorted(set(re.findall(pattern, html)))

    def key(name):
        nums = re.findall(r"\d+", name)
        return tuple(int(x) for x in nums[:3])

    names.sort(key=key)
    return names


def get_latest_anaconda_installer():
    print_step("从清华 TUNA 镜像解析最新完整 Anaconda Windows x86_64 安装包")
    try:
        html = urlopen_text_with_retry(TUNA_ANACONDA_ARCHIVE_URL)
        installers = parse_anaconda_windows_installers(html)
        if installers:
            latest = installers[-1]
            print("解析到最新安装包：" + latest)
            return TUNA_ANACONDA_ARCHIVE_URL + latest, latest
    except Exception as e:
        print("清华 TUNA 解析失败：" + str(e))

    print("使用备用安装包文件名：" + ANACONDA_FALLBACK_FILE)
    return TUNA_ANACONDA_ARCHIVE_URL + ANACONDA_FALLBACK_FILE, ANACONDA_FALLBACK_FILE


def download_file_with_retry(url, dst):
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    last_error = None
    for attempt in range(1, DOWNLOAD_RETRIES + 1):
        try:
            if dst.exists() and dst.stat().st_size > 100 * 1024 * 1024:
                print("检测到本地已有安装包，跳过下载：" + str(dst))
                return

            temp = dst.with_suffix(dst.suffix + ".part")
            if temp.exists():
                temp.unlink()

            print("\n下载地址：" + url)
            print("保存到：" + str(dst))
            print("第 {}/{} 次下载".format(attempt, DOWNLOAD_RETRIES))

            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
                total = resp.headers.get("Content-Length")
                total = int(total) if total and total.isdigit() else 0
                done = 0
                t0 = time.time()

                with open(temp, "wb") as f:
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)

                        if total:
                            percent = done * 100 / total
                            mb_done = done / (1024 * 1024)
                            mb_total = total / (1024 * 1024)
                            elapsed = max(time.time() - t0, 0.1)
                            speed = mb_done / elapsed
                            sys.stdout.write(
                                "\r进度：{:.1f}%  {:.1f}/{:.1f} MB  {:.1f} MB/s".format(
                                    percent, mb_done, mb_total, speed
                                )
                            )
                            sys.stdout.flush()

            if total and temp.stat().st_size < total:
                raise RuntimeError("下载文件大小不完整。")

            temp.replace(dst)
            print("\n下载完成。")
            return

        except Exception as e:
            last_error = e
            print("\n下载失败，第 {}/{} 次：{}".format(attempt, DOWNLOAD_RETRIES, e))
            if attempt < DOWNLOAD_RETRIES:
                print("{} 秒后重试。".format(DOWNLOAD_RETRY_SLEEP))
                time.sleep(DOWNLOAD_RETRY_SLEEP)

    if url.startswith(TUNA_ANACONDA_ARCHIVE_URL):
        fallback_url = url.replace(TUNA_ANACONDA_ARCHIVE_URL, OFFICIAL_ANACONDA_ARCHIVE_URL)
        print("\n清华源多次失败，尝试官方源兜底：")
        return download_file_with_retry(fallback_url, dst)

    raise RuntimeError("文件下载失败：" + str(last_error))


def find_existing_conda():
    candidates = []

    conda_in_path = which("conda")
    if conda_in_path:
        candidates.append(Path(conda_in_path))

    common_dirs = [
        Path(DEFAULT_ANACONDA_DIR),
        Path("C:/ProgramData/Anaconda3"),
        Path("C:/Anaconda3"),
        Path.home() / "Anaconda3",
        Path.home() / "anaconda3",
    ]

    for d in common_dirs:
        candidates.append(d / "Scripts" / "conda.exe")
        candidates.append(d / "condabin" / "conda.bat")

    for c in candidates:
        try:
            if c.exists():
                return c
        except Exception:
            pass

    return None


def get_conda_root(conda_path):
    p = Path(conda_path).resolve()
    if p.name.lower() == "conda.exe" and p.parent.name.lower() == "scripts":
        return p.parent.parent
    if p.name.lower() == "conda.bat" and p.parent.name.lower() == "condabin":
        return p.parent.parent
    return p.parent.parent


def ensure_conda(project_dir):
    print_title("检查完整 Anaconda / conda")

    existing = find_existing_conda()
    if existing:
        print("检测到已有 conda：")
        print(str(existing))
        try:
            assert_clean_path(existing, "已有 conda 路径")
        except RuntimeError as e:
            print(str(e))
            print("该路径存在风险，本脚本不建议继续使用。")
            existing = None

        if existing:
            choice = input("是否直接使用已有 conda？[Y/n] 默认 Y：\n> ").strip().lower()
            if choice not in ("n", "no"):
                return existing

    print("\n未使用已有 conda，将下载并安装完整 Anaconda Distribution。")
    print("注意：完整 Anaconda 安装包约 1GB，安装后占用空间较大。")
    print("继续安装表示你同意 Anaconda 官方许可/服务条款。")
    agree = input("是否继续？[Y/n] 默认 Y：\n> ").strip().lower()
    if agree in ("n", "no"):
        raise RuntimeError("用户取消 Anaconda 安装。")

    url, installer_name = get_latest_anaconda_installer()
    installer_path = Path(project_dir) / "downloads" / installer_name
    download_file_with_retry(url, installer_path)

    install_dir = choose_clean_dir("选择 Anaconda 安装目录", DEFAULT_ANACONDA_DIR)
    install_dir.parent.mkdir(parents=True, exist_ok=True)

    print_step("静默安装完整 Anaconda")
    print("安装包：" + str(installer_path))
    print("安装目录：" + str(install_dir))

    cmd = [
        str(installer_path),
        "/InstallationType=JustMe",
        "/RegisterPython=0",
        "/AddToPath=0",
        "/S",
        "/D=" + str(install_dir),
    ]
    run_cmd(cmd)

    conda_exe = install_dir / "Scripts" / "conda.exe"
    conda_bat = install_dir / "condabin" / "conda.bat"
    if conda_exe.exists():
        return conda_exe
    if conda_bat.exists():
        return conda_bat
    raise RuntimeError("Anaconda 安装后未找到 conda，请检查安装目录。")


def conda_cmd(conda_path, args, check=True, capture=False):
    return run_cmd([str(conda_path)] + list(args), check=check, capture=capture)


def conda_env_list(conda_path):
    out = conda_cmd(conda_path, ["env", "list", "--json"], capture=True, check=False)
    try:
        data = json.loads(out)
        return [Path(x) for x in data.get("envs", [])]
    except Exception:
        return []


def find_env_path(conda_path, env_name):
    for p in conda_env_list(conda_path):
        if p.name.lower() == env_name.lower():
            return p
    root = get_conda_root(conda_path)
    p = root / "envs" / env_name
    if p.exists():
        return p
    return None


def get_env_python(conda_path, env_name):
    env_path = find_env_path(conda_path, env_name)
    if not env_path:
        raise RuntimeError("未找到 conda 环境：" + env_name)
    py = env_path / "python.exe"
    if not py.exists():
        py = env_path / "Scripts" / "python.exe"
    if not py.exists():
        raise RuntimeError("未找到环境内部 python.exe：" + str(env_path))
    return py


def create_or_reuse_env(conda_path):
    global CONDA_ENV_NAME

    print_title("创建 / 复用 conda 环境")

    env_path = find_env_path(conda_path, CONDA_ENV_NAME)
    if env_path:
        print("检测到已有环境：{} -> {}".format(CONDA_ENV_NAME, env_path))
        print("1. 复用现有环境")
        print("2. 删除后重建")
        print("3. 换一个环境名")
        choice = input("请选择 [1/2/3]，默认 1：\n> ").strip() or "1"

        if choice == "2":
            conda_cmd(conda_path, ["env", "remove", "-n", CONDA_ENV_NAME, "-y"])
        elif choice == "3":
            new_name = input("请输入新的环境名，例如 yolo310：\n> ").strip()
            if new_name:
                CONDA_ENV_NAME = new_name
            if find_env_path(conda_path, CONDA_ENV_NAME):
                print("新环境名已存在，将复用。")
                return
            conda_cmd(conda_path, ["create", "-n", CONDA_ENV_NAME, "python=" + CONDA_PYTHON_VERSION, "-y"])
            return
        else:
            return

    print("正在创建环境：{}，Python {}".format(CONDA_ENV_NAME, CONDA_PYTHON_VERSION))
    conda_cmd(conda_path, ["create", "-n", CONDA_ENV_NAME, "python=" + CONDA_PYTHON_VERSION, "-y"])


def choose_torch_backend(nvidia_info):
    print_title("选择 PyTorch 安装方式")

    auto_choice = "cpu"
    cuda_driver = nvidia_info.get("cuda_driver")

    if nvidia_info.get("available") and cuda_driver:
        try:
            v = float(cuda_driver)
            if v >= 12.8:
                auto_choice = "cu128"
            elif v >= 12.6:
                auto_choice = "cu126"
            elif v >= 11.8:
                auto_choice = "cu118"
            else:
                auto_choice = "cpu"
        except Exception:
            auto_choice = "cu118"

    print("自动建议：" + auto_choice)
    print("1. 自动选择")
    print("2. CPU 版，兼容最好但速度慢")
    print("3. CUDA 11.8 版")
    print("4. CUDA 12.6 版")
    print("5. CUDA 12.8 版")
    print("6. 跳过 PyTorch 安装")

    c = input("请选择 [1/2/3/4/5/6]，默认 1：\n> ").strip() or "1"
    if c == "1":
        return auto_choice
    if c == "2":
        return "cpu"
    if c == "3":
        return "cu118"
    if c == "4":
        return "cu126"
    if c == "5":
        return "cu128"
    if c == "6":
        return "skip"
    return auto_choice


def choose_pypi_source():
    print_title("选择普通 Python 包下载源")
    print("1. 官方 PyPI")
    print("2. 清华 PyPI 镜像，国内下载通常更快")
    print("注意：PyTorch 仍使用 PyTorch 官方 wheel 源。")
    c = input("请选择 [1/2]，默认 2：\n> ").strip() or "2"
    if c == "2":
        return "https://pypi.tuna.tsinghua.edu.cn/simple"
    return None


def pip_install(env_python, packages, pypi_source=None, extra_args=None, group_name="packages"):
    if not packages:
        return

    print_step("安装 " + group_name)
    cmd = [str(env_python), "-m", "pip", "install", "--default-timeout=1000"] + list(packages)
    if pypi_source:
        cmd += ["-i", pypi_source]
    if extra_args:
        cmd += list(extra_args)
    run_cmd(cmd)


def install_all_packages(env_python, torch_backend, pypi_source):
    print_title("安装 YOLO 工具包")

    pip_install(env_python, ["--upgrade", "pip", "setuptools", "wheel"], pypi_source, group_name="pip / setuptools / wheel")

    if torch_backend != "skip":
        if torch_backend not in TORCH_INDEX:
            raise RuntimeError("未知 PyTorch 后端：" + str(torch_backend))
        pip_install(
            env_python,
            TORCH_PACKAGES,
            None,
            ["--index-url", TORCH_INDEX[torch_backend]],
            group_name="PyTorch " + torch_backend,
        )
    else:
        print("跳过 PyTorch 安装。")

    pip_install(env_python, BASIC_PACKAGES, pypi_source, group_name="YOLO 基础依赖")
    pip_install(env_python, EXPORT_PACKAGES, pypi_source, group_name="ONNX 导出/部署依赖")
    pip_install(env_python, HARDWARE_PACKAGES, pypi_source, group_name="硬件驱动依赖 pyserial / pyrealsense2")


def choose_project_dir():
    p = choose_clean_dir("选择 YOLO 项目目录", DEFAULT_PROJECT_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


def choose_model():
    print_title("选择 YOLO 模型")
    for k, item in YOLO_MODEL_MENU.items():
        print("{:>2}. {:<42} -> {}".format(k, item[0], item[1]))

    c = input("请选择模型编号，默认 9 YOLO11n：\n> ").strip() or "9"
    if c not in YOLO_MODEL_MENU:
        c = "9"
    desc, model_name = YOLO_MODEL_MENU[c]

    if model_name == "CUSTOM":
        model_name = input("请输入模型路径，例如 best.pt：\n> ").strip().strip('"')
        if not model_name:
            model_name = "best.pt"

    return desc, model_name


def write_project_files(project_dir, conda_path, env_python, model_name, torch_backend, pypi_source, sys_report):
    print_step("生成测试脚本、启动脚本、环境记录")

    project_dir = Path(project_dir)

    test_yolo = '''# -*- coding: utf-8 -*-
from ultralytics import YOLO
import torch

MODEL = r"{model_name}"

print("torch version:", torch.__version__)
print("cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("gpu:", torch.cuda.get_device_name(0))

model = YOLO(MODEL)
print("模型加载成功:", MODEL)

results = model.predict(
    source="https://ultralytics.com/images/bus.jpg",
    show=False,
    save=True
)

print("预测完成，结果保存在 runs/detect/predict 目录。")
'''.format(model_name=model_name)

    test_camera = '''# -*- coding: utf-8 -*-
from ultralytics import YOLO
import cv2
import torch

MODEL = r"{model_name}"

print("torch version:", torch.__version__)
print("cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("gpu:", torch.cuda.get_device_name(0))

model = YOLO(MODEL)

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
if not cap.isOpened():
    raise RuntimeError("摄像头打开失败，请检查摄像头编号、权限或是否被其他软件占用。")

while True:
    ret, frame = cap.read()
    if not ret:
        print("读取摄像头失败")
        break

    results = model.predict(frame, imgsz=640, conf=0.25, verbose=False)
    annotated = results[0].plot()

    cv2.imshow("YOLO Camera Test - Press q to quit", annotated)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
'''.format(model_name=model_name)

    test_realsense = '''# -*- coding: utf-8 -*-
# RealSense D435i / D400 系列基础检测脚本
import pyrealsense2 as rs

ctx = rs.context()
devices = ctx.query_devices()

print("检测到 RealSense 设备数量:", len(devices))
if len(devices) == 0:
    print("未检测到 RealSense 设备，请检查 USB 连接、驱动、固件和 RealSense Viewer。")
else:
    for i, dev in enumerate(devices):
        print("\\n[设备 {}]".format(i))
        for info in [
            rs.camera_info.name,
            rs.camera_info.serial_number,
            rs.camera_info.firmware_version,
            rs.camera_info.product_line,
        ]:
            try:
                print("{}: {}".format(info, dev.get_info(info)))
            except Exception:
                pass

print("\\npyrealsense2 导入成功，RealSense Python 环境可用。")
print("\\n正式联调提醒：")
print("1. 使用 YOLO 二维框 + 深度流做三维坐标解算前，请先用 Intel RealSense Viewer 检查设备固件状态。")
print("2. D435i / D430I / D400 系列长时间跑流前，建议确认固件版本与当前 pyrealsense2 / librealsense 代际匹配。")
print("3. 如果出现掉帧、深度图撕裂、RGB 不出图或 Frame didn't arrive，请优先检查 USB3.0 连接、固件版本和 RealSense Viewer 中的流配置。")
'''

    export_onnx = '''# -*- coding: utf-8 -*-
from ultralytics import YOLO

MODEL = r"{model_name}"

model = YOLO(MODEL)
model.export(format="onnx", imgsz=640, opset=12, simplify=True)

print("ONNX 导出完成。")
'''.format(model_name=model_name)

    conda_root = get_conda_root(conda_path)
    activate_bat = conda_root / "Scripts" / "activate.bat"
    open_env_bat = '''@echo off
chcp 65001 >nul
echo 激活 Anaconda YOLO 环境...
call "{activate_bat}" {env_name}
cd /d "{project_dir}"
cmd
'''.format(
        activate_bat=str(activate_bat),
        env_name=CONDA_ENV_NAME,
        project_dir=str(project_dir),
    )

    run_test_bat = '''@echo off
chcp 65001 >nul
cd /d "{project_dir}"
"{env_python}" test_yolo.py
pause
'''.format(project_dir=str(project_dir), env_python=str(env_python))

    requirements = []
    requirements.append("# YOLO Anaconda full deployment V3")
    requirements.append("# generated at " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    requirements.append("# conda env: " + CONDA_ENV_NAME)
    requirements.append("# python: " + CONDA_PYTHON_VERSION)
    requirements.append("# torch backend: " + torch_backend)
    requirements.append("")
    requirements.extend(TORCH_PACKAGES)
    requirements.append("")
    requirements.append("# basic")
    requirements.extend(BASIC_PACKAGES)
    requirements.append("")
    requirements.append("# export")
    requirements.extend(EXPORT_PACKAGES)
    requirements.append("")
    requirements.append("# hardware")
    requirements.extend(HARDWARE_PACKAGES)
    requirements.append("")

    report = dict(sys_report)
    report.update({
        "conda_path": str(conda_path),
        "conda_env": CONDA_ENV_NAME,
        "env_python": str(env_python),
        "torch_backend": torch_backend,
        "pypi_source": pypi_source or "official",
        "selected_model": model_name,
        "project_dir": str(project_dir),
        "basic_packages": BASIC_PACKAGES,
        "export_packages": EXPORT_PACKAGES,
        "hardware_packages": HARDWARE_PACKAGES,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })

    (project_dir / "test_yolo.py").write_text(test_yolo, encoding="utf-8")
    (project_dir / "test_camera.py").write_text(test_camera, encoding="utf-8")
    (project_dir / "test_realsense.py").write_text(test_realsense, encoding="utf-8")
    (project_dir / "export_onnx.py").write_text(export_onnx, encoding="utf-8")
    (project_dir / "open_yolo_env.bat").write_text(open_env_bat, encoding="utf-8")
    (project_dir / "run_test_yolo.bat").write_text(run_test_bat, encoding="utf-8")
    (project_dir / "requirements_yolo.txt").write_text("\n".join(requirements), encoding="utf-8")
    (project_dir / "install_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def verify_install(env_python, project_dir):
    print_title("验证安装")
    code = r'''
import sys
import torch
import cv2
import ultralytics

print("Python:", sys.version)
print("torch:", torch.__version__)
print("torch cuda available:", torch.cuda.is_available())
print("torch cuda version:", torch.version.cuda)
if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
print("OpenCV:", cv2.__version__)
print("Ultralytics:", ultralytics.__version__)

try:
    import serial
    print("pyserial: OK")
except Exception as e:
    print("pyserial: FAIL", e)

try:
    import pyrealsense2 as rs
    print("pyrealsense2: OK")
except Exception as e:
    print("pyrealsense2: FAIL", e)
    raise
'''
    run_cmd([str(env_python), "-c", code], cwd=project_dir)


def test_model(env_python, project_dir, model_name):
    print_title("下载并测试 YOLO 模型")
    code = '''
from ultralytics import YOLO
import torch

model_name = r"{model_name}"
print("准备加载模型:", model_name)
model = YOLO(model_name)
print("模型加载成功:", model_name)
print("CUDA available:", torch.cuda.is_available())

results = model.predict(
    source="https://ultralytics.com/images/bus.jpg",
    show=False,
    save=True,
    verbose=True
)
print("测试完成。")
'''.format(model_name=model_name)
    run_cmd([str(env_python), "-c", code], cwd=project_dir)


def print_final(project_dir, conda_path, env_python, model_name):
    print_title("部署完成")
    print("YOLO 项目目录：" + str(project_dir))
    print("conda 路径：" + str(conda_path))
    print("conda 环境：" + CONDA_ENV_NAME)
    print("环境 Python：" + str(env_python))
    print("模型：" + model_name)

    print("\n后续使用方法 1：双击/运行")
    print("  " + str(Path(project_dir) / "open_yolo_env.bat"))

    print("\n后续使用方法 2：无需激活，直接调用环境 python")
    print('  cd /d "{}"'.format(project_dir))
    print('  "{}" test_yolo.py'.format(env_python))
    print('  "{}" test_camera.py'.format(env_python))
    print('  "{}" test_realsense.py'.format(env_python))
    print('  "{}" export_onnx.py'.format(env_python))


def main():
    print_title("Windows + 完整 Anaconda + YOLO 工程部署工具 V3")

    if not is_windows():
        raise RuntimeError("此脚本主要用于 Windows。当前系统不是 Windows。")

    launcher_python = ensure_launcher_python_ok()
    cpu_name, cpu_cores = get_cpu_info()
    mem_gb = get_memory_gb()
    disk_gb = get_disk_free_gb(Path.cwd())
    nvidia_info = get_nvidia_info()
    nvcc_version = get_nvcc_version()

    print_title("系统检测结果")
    print("系统：" + platform.platform())
    print("管理员权限：" + ("是" if is_admin() else "否，JustMe 安装通常不需要管理员权限"))
    print("启动脚本的 Python：" + launcher_python["version"] + " / " + launcher_python["bits"])
    print("Python 路径：" + launcher_python["executable"])
    print("CPU：" + str(cpu_name))
    print("CPU 核心数：" + str(cpu_cores))
    print("内存：" + ("{:.1f} GB".format(mem_gb) if mem_gb else "未知"))
    print("当前磁盘剩余：" + "{:.1f} GB".format(disk_gb))
    print("nvidia-smi：" + str(which("nvidia-smi") or "未找到"))
    print("nvcc：" + str(nvcc_version or "未安装 CUDA Toolkit，普通 PyTorch 不强制需要"))

    if nvidia_info.get("available"):
        print("\nNVIDIA 显卡：检测到")
        print("驱动支持 CUDA Runtime 最高版本：" + str(nvidia_info.get("cuda_driver")))
        for i, gpu in enumerate(nvidia_info.get("gpus", []), 1):
            print("  GPU{}: {} / 显存 {} / 驱动 {}".format(i, gpu["name"], gpu["memory"], gpu["driver"]))
    else:
        print("\nNVIDIA 显卡：未检测到")
        print("原因：" + nvidia_info.get("reason", ""))

    if disk_gb < 25:
        print("\n警告：完整 Anaconda + PyTorch + YOLO 建议至少预留 25GB 磁盘空间。")

    project_dir = choose_project_dir()
    conda_path = ensure_conda(project_dir)

    print_title("conda 检查")
    conda_cmd(conda_path, ["--version"], check=False)
    conda_cmd(conda_path, ["info"], check=False)

    create_or_reuse_env(conda_path)
    env_python = get_env_python(conda_path, CONDA_ENV_NAME)

    model_desc, model_name = choose_model()
    torch_backend = choose_torch_backend(nvidia_info)
    pypi_source = choose_pypi_source()

    print_title("安装确认")
    print("项目目录：" + str(project_dir))
    print("conda：" + str(conda_path))
    print("环境名：" + CONDA_ENV_NAME)
    print("环境 Python：" + str(env_python))
    print("Python：" + CONDA_PYTHON_VERSION)
    print("YOLO 模型：" + model_name)
    print("PyTorch 后端：" + torch_backend)
    print("普通包下载源：" + (pypi_source or "官方 PyPI"))
    print("硬件依赖：" + ", ".join(HARDWARE_PACKAGES))
    ok = input("确认开始安装 YOLO 工具包？[Y/n] 默认 Y：\n> ").strip().lower()
    if ok in ("n", "no"):
        print("用户取消。")
        return

    sys_report = {
        "platform": platform.platform(),
        "launcher_python": launcher_python,
        "cpu": {"name": cpu_name, "cores": cpu_cores},
        "memory_gb": mem_gb,
        "disk_free_gb": disk_gb,
        "nvidia": nvidia_info,
        "nvcc": nvcc_version,
    }

    install_all_packages(env_python, torch_backend, pypi_source)
    write_project_files(project_dir, conda_path, env_python, model_name, torch_backend, pypi_source, sys_report)
    verify_install(env_python, project_dir)

    test_now = input("是否现在下载并测试所选 YOLO 模型？[Y/n] 默认 Y：\n> ").strip().lower()
    if test_now not in ("n", "no"):
        try:
            test_model(env_python, project_dir, model_name)
        except Exception as e:
            print("\n模型下载或测试失败，但环境可能已经安装成功。")
            print("常见原因：网络无法访问模型下载地址、代理问题、当前 ultralytics 不支持该模型名。")
            print("错误：" + str(e))

    print_final(project_dir, conda_path, env_python, model_name)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户中断。")
    except Exception as e:
        print_title("部署失败")
        print(str(e))
        print("\n排查建议：")
        print("1. 确认启动脚本的 Python 是 64 位，建议 3.10 或 3.11。")
        print("2. 确认网络能访问清华 TUNA 镜像、PyPI、download.pytorch.org。")
        print("3. 如果 CUDA 版 PyTorch 安装失败，重新运行脚本并选择 CPU 版。")
        print("4. 安装路径必须是纯英文、无空格，例如 C:\\Users\\Public\\Anaconda3_YOLO。")
        print("5. pyrealsense2 安装失败时，优先确认环境 Python 是 3.10 且系统为 64 位 Windows。")
        sys.exit(1)
