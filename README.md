# YOLO One-Click Installer

Windows 下的 YOLO 一键部署脚本。它会自动检测系统环境，安装或复用 Anaconda，创建 `yolo` conda 环境，并安装 Ultralytics YOLO、PyTorch、ONNX 导出工具以及常见硬件依赖。

## 功能

- 自动检测 Windows、Python、CPU、内存、磁盘空间和 NVIDIA 显卡信息
- 自动安装或复用 Anaconda
- 自动创建或复用 `yolo` conda 环境
- 支持 CPU、CUDA 11.8、CUDA 12.6、CUDA 12.8 等 PyTorch 安装源
- 支持清华 PyPI 镜像或官方 PyPI
- 支持 YOLOv8、YOLOv9、YOLOv10、YOLO11 常见模型
- 自动生成测试脚本、环境启动脚本、导出 ONNX 脚本和部署报告
- 包含 `pyserial`、`pyrealsense2` 等硬件依赖

## 运行要求

- Windows 10/11 64 位
- Python 3.8 或更高版本，建议 Python 3.10/3.11
- 至少 25GB 可用磁盘空间
- 网络可访问 Anaconda、PyPI 和 PyTorch 下载源
- 如果需要 GPU 加速，请先安装 NVIDIA 显卡驱动

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
6. 是否立即下载并测试模型

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
- `test_yolo.py`：YOLO 模型测试脚本
- `test_camera.py`：摄像头测试脚本
- `test_realsense.py`：Intel RealSense 测试脚本
- `export_onnx.py`：ONNX 导出脚本
- `requirements_yolo.txt`：部署环境依赖记录
- `system_report.json`：系统检测报告

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
