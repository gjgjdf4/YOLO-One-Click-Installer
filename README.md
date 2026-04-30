# YOLO One-Click Installer

Windows 下的 YOLO 一键部署脚本。它会自动检测系统环境，安装或复用 Anaconda，创建 `yolo` conda 环境，并安装 Ultralytics YOLO、PyTorch、ONNX 导出工具以及常见硬件依赖。

## 功能

- 自动检测 Windows、Python、CPU、内存、磁盘空间和 NVIDIA 显卡信息
- 自动安装或复用 Anaconda
- 自动创建或复用 `yolo` conda 环境
- 固定核心依赖版本，降低 PyTorch、Ultralytics、OpenCV、ONNX、RealSense 之间的冲突风险
- 支持 CPU、CUDA 11.8、CUDA 12.6、CUDA 12.8 等 PyTorch 2.7.0 安装源
- 支持清华 PyPI 镜像或官方 PyPI
- 支持 YOLOv8、YOLOv9、YOLOv10、YOLO11、YOLO12、YOLO26 常见模型
- 自动生成测试脚本、环境启动脚本、导出 ONNX 脚本和部署报告
- 可选安装 PyCharm Community，并生成 PyCharm 项目配置
- 包含 `pyserial`、`pyrealsense2` 等硬件依赖

## 运行要求

- Windows 10/11 64 位
- Python 3.8 或更高版本，建议 Python 3.10/3.11
- 至少 25GB 可用磁盘空间
- 网络可访问 Anaconda、PyPI 和 PyTorch 下载源
- 如果需要 GPU 加速，请先安装 NVIDIA 显卡驱动

## 稳定版本策略

脚本默认使用一套统一稳定环境，优先保证多个 YOLO 版本共用一个 conda 环境：

| 工具 | 固定版本 |
| --- | --- |
| Python | 3.10.x |
| PyTorch | 2.7.0 |
| torchvision | 0.22.0 |
| torchaudio | 2.7.0 |
| ultralytics | 8.4.45 |
| opencv-python | 4.13.0.92 |
| onnx | 1.21.0 |
| onnxruntime | 1.25.1 |
| pyserial | 3.5 |
| pyrealsense2 | 2.57.7.10387 |

CUDA 后端仍按 `nvidia-smi` 自动选择：

| nvidia-smi CUDA Version | PyTorch 后端 |
| --- | --- |
| 无 NVIDIA / 无 nvidia-smi | CPU |
| 小于 11.8 | CPU |
| 11.8 到 12.5 | cu118 |
| 12.6 到 12.7 | cu126 |
| 12.8 及以上 | cu128 |

部署完成后，脚本会校验关键包版本，避免安装过程被 pip 自动解析成不一致的版本组合。

## 快速开始

在 PowerShell 或 CMD 中运行：

```powershell
python yolo.py
```

脚本会进入交互式流程，按提示选择：

1. 项目安装目录
2. 是否使用已有 conda
3. YOLO 模型
4. PyTorch 后端
5. Python 包下载源
6. 是否安装或配置 PyCharm
7. 是否立即下载并测试模型

## 默认路径

脚本默认使用以下目录：

```text
C:\Users\Public\Anaconda3_YOLO
C:\Users\Public\YOLO_Anaconda_Deploy
```

安装路径建议使用纯英文且不包含空格，否则脚本会拒绝继续，以避免 Windows 下常见路径兼容问题。

## 部署后生成的文件

脚本完成后，会在目标项目目录中生成：

- `open_yolo_env.bat`：打开 YOLO conda 环境
- `open_in_pycharm.bat`：用 PyCharm 打开当前 YOLO 项目
- `test_yolo.py`：YOLO 模型测试脚本
- `test_camera.py`：摄像头测试脚本
- `test_realsense.py`：Intel RealSense 测试脚本
- `export_onnx.py`：ONNX 导出脚本
- `requirements_yolo.txt`：部署环境依赖记录
- `install_report.json`：系统检测和安装报告
- `.idea/`：PyCharm 项目配置和运行配置

## PyCharm 支持

脚本提供 3 种 PyCharm 选项：

1. 只配置项目文件：适合电脑上已经安装 PyCharm 的情况
2. 下载并安装 PyCharm Community，然后配置项目文件
3. 跳过 PyCharm

配置完成后，可以双击目标项目目录里的 `open_in_pycharm.bat`，也可以在 PyCharm 中直接打开目标项目目录。项目配置会指向脚本创建的 conda 环境 Python，并预置 `Run test_yolo` 和 `Export ONNX` 两个运行配置。

## 常见问题

### 路径包含中文或空格

请改用纯英文路径，例如：

```text
C:\Users\Public\YOLO_Anaconda_Deploy
```

### CUDA 版 PyTorch 安装失败

重新运行脚本并选择 CPU 版，确认基础环境可用后，再根据显卡驱动版本选择合适 CUDA 后端。

### pyrealsense2 安装失败

优先确认系统是 64 位 Windows，并且 conda 环境 Python 版本为 3.10。

## 许可

本项目使用 MIT License。
