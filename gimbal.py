"""
云台控制模块
使用 PCA9685 + adafruit-servokit 控制俯仰舵机
俯仰轴接 Channel 0
"""

import time
from adafruit_servokit import ServoKit


class Gimbal:
    # 俯仰角度限制(单位:度)
    TILT_MIN = 0    # 0° = 水平正前方
    TILT_MAX = 150   # 90° = 垂直向上(不建议去到,一般 60° 够用)

    # 每次转动后的稳定等待时间
    SETTLE_TIME = 0.6  # 秒,等舵机到位+画面稳定

    def __init__(self, channel_tilt=0):
        """
        channel_tilt: 俯仰舵机接在 PCA9685 的哪个通道(默认 0)
        """
        self.kit = ServoKit(channels=16)
        self.ch = channel_tilt
        self.current_angle = 0
        self.home()  # 初始化时归位

    def set_angle(self, angle, wait=True):
        """设置俯仰角度
        angle: 0=水平, 正数=向上仰
        wait: 是否等待舵机到位
        """
        angle = max(self.TILT_MIN, min(self.TILT_MAX, angle))
        self.kit.servo[self.ch].angle = angle
        self.current_angle = angle
        if wait:
            time.sleep(self.SETTLE_TIME)

    def home(self):
        """归位到水平(60°)"""
        self.set_angle(60)

    def sweep(self, angles):
        """按角度列表依次转动,返回每个角度的时间戳
        
        用法:
            for angle, ts in gimbal.sweep([0, 30, 60]):
                # 此时舵机已到位,可以拍照
                ...
        """
        for angle in angles:
            self.set_angle(angle)
            yield angle

    def cleanup(self):
        self.home()


# 自测
if __name__ == "__main__":
    print("=== 云台自测 ===")
    g = Gimbal()
    try:
        for angle in [0, 60, 90, 135, 90, 60,0]:
            print(f"转到 {angle}°")
            g.set_angle(angle)
            time.sleep(1)
        print("自测完成 ✓")
    finally:
        g.cleanup()
