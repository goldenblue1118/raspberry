"""
摄像头独立测试脚本
用于验证 OV5647 + picamera2 是否正常工作
"""

from picamera2 import Picamera2
import time
import os


def main():
    print("=== OV5647 摄像头测试 ===")

    picam2 = Picamera2()
    print("摄像头列表:")
    for cam in Picamera2.global_camera_info():
        print(f"  - {cam}")

    config = picam2.create_still_configuration(
        main={"size": (2592, 1944)}
    )
    picam2.configure(config)
    picam2.start()

    print("等待曝光稳定...")
    time.sleep(2)

    out_path = "test_shot.jpg"
    picam2.capture_file(out_path)
    picam2.stop()

    size = os.path.getsize(out_path)
    print(f"拍照成功: {out_path} ({size/1024:.1f} KB)")
    print("如果图像偏暗/偏糊,需要:")
    print("  1. 调焦距")
    print("  2. 增加光照或加补光灯")


if __name__ == "__main__":
    main()
