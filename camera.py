"""
摄像头与图像预处理模块

功能:
  - 通过 picamera2 控制 OV5647 拍照
  - 拉普拉斯方差清晰度评估
  - CLAHE 对比度增强
  - 图像预处理 pipeline
"""

import os
import time
from datetime import datetime

import cv2
import numpy as np

try:
    from picamera2 import Picamera2
    HAS_PICAMERA = True
except ImportError:
    HAS_PICAMERA = False
    print("[WARN] picamera2 未安装,Camera 类无法使用真实摄像头")


# 默认拍照分辨率(OV5647 原生 2592×1944)
DEFAULT_RESOLUTION = (2592, 1944)
# 清晰度阈值,实测后调整
DEFAULT_BLUR_THRESHOLD = 100.0


class Camera:
    """OV5647 摄像头封装"""

    def __init__(self, resolution=DEFAULT_RESOLUTION, save_dir="captures"):
        if not HAS_PICAMERA:
            raise RuntimeError("picamera2 未安装")

        self.resolution = resolution
        self.save_dir = save_dir
        os.makedirs(save_dir, exist_ok=True)

        self.picam2 = Picamera2()
        config = self.picam2.create_still_configuration(
            main={"size": resolution, "format": "RGB888"}
        )
        self.picam2.configure(config)
        self.picam2.start()
        # 等待自动曝光稳定
        time.sleep(2)

    def capture(self):
        """拍照,返回 BGR 格式 numpy 数组(供 OpenCV 使用)"""
        rgb = self.picam2.capture_array()
        # picamera2 返回 RGB,OpenCV 需要 BGR
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        return bgr

    def capture_with_quality_check(self, max_retry=3,
                                   threshold=DEFAULT_BLUR_THRESHOLD):
        """拍照并做清晰度评估,糊了自动重拍

        返回: (image, blur_score, quality_ok)
        """
        last_img = None
        last_score = 0.0
        for i in range(max_retry):
            img = self.capture()
            score = blur_score(img)
            last_img, last_score = img, score
            if score >= threshold:
                return img, score, True
            # 重拍前给一个短暂等待(可能是震动还没消除)
            time.sleep(0.3)
        return last_img, last_score, False

    def save(self, image, prefix="img"):
        """保存图像到 save_dir,返回完整路径"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        path = os.path.join(self.save_dir, f"{prefix}_{ts}.jpg")
        cv2.imwrite(path, image, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return path

    def close(self):
        try:
            self.picam2.stop()
        except Exception:
            pass


# ============= 图像处理函数 =============

def blur_score(image):
    """拉普拉斯方差清晰度评估
    数值越大越清晰。经验阈值:
        < 50:  明显模糊
        50-100: 边缘
        > 100: 较清晰
        > 200: 非常清晰
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) \
        if len(image.shape) == 3 else image
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def preprocess(image, save_intermediate=False):
    """裂纹检测预处理 pipeline

    步骤:
        1. 灰度化
        2. CLAHE 自适应直方图均衡(增强对比度)
        3. 高斯降噪

    参数:
        image: BGR 输入图像
        save_intermediate: 是否返回中间结果(用于调试展示)

    返回:
        预处理后的灰度图(单通道),或字典(若 save_intermediate=True)
    """
    # 1. 灰度化
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 2. CLAHE
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # 3. 高斯降噪
    denoised = cv2.GaussianBlur(enhanced, (3, 3), 0)

    if save_intermediate:
        return {
            'gray': gray,
            'clahe': enhanced,
            'denoised': denoised,
            'final': denoised,
        }
    return denoised


def draw_score(image, score, ok):
    """在图像左上角绘制清晰度评分(用于演示和调试)"""
    img = image.copy()
    color = (0, 255, 0) if ok else (0, 0, 255)
    text = f"Blur: {score:.1f} {'OK' if ok else 'BLUR'}"
    cv2.putText(img, text, (20, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, color, 3)
    return img


# ============= 自测主程序 =============
if __name__ == "__main__":
    print("=== 摄像头自测程序 ===")
    cam = Camera()
    try:
        print("拍照中...")
        img, score, ok = cam.capture_with_quality_check()
        print(f"清晰度评分: {score:.1f}")
        print(f"质量检查: {'通过 ✓' if ok else '不通过(模糊)✗'}")

        # 保存原图
        raw_path = cam.save(img, prefix="raw")
        print(f"原图: {raw_path}")

        # 保存预处理图
        processed = preprocess(img)
        proc_path = os.path.join(cam.save_dir,
                                 os.path.basename(raw_path).replace(
                                     "raw_", "proc_"))
        cv2.imwrite(proc_path, processed)
        print(f"预处理图: {proc_path}")

        # 保存带分数的演示图
        annotated = draw_score(img, score, ok)
        ann_path = os.path.join(cam.save_dir,
                                os.path.basename(raw_path).replace(
                                    "raw_", "annotated_"))
        cv2.imwrite(ann_path, annotated)
        print(f"标注图: {ann_path}")

    finally:
        cam.close()
