 #coding=utf-8

import os
import json
import gzip
import uuid
import asyncio
import websockets
from typing import Dict, Optional
from pathlib import Path

class TTSService:
    def __init__(self, app=None):
        self.app = app
        self.voice_settings = {
            "Merlin": {
                "voice_type": "ICL_zh_male_guiyishenmi_tob",
                "encoding": "mp3",
                "speed_ratio": 1.0,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
            "Percival": {
                "voice_type": "ICL_zh_male_guzhibingjiao_tob",
                "encoding": "mp3",
                "speed_ratio": 1.0,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
            "Knight": {
                "voice_type": "ICL_zh_male_lvchaxiaoge_tob",
                "encoding": "mp3",
                "speed_ratio": 1.0,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
            "Morgana": {
                "voice_type": "ICL_zh_female_wumeiyujie_tob",
                "encoding": "mp3",
                "speed_ratio": 1.0,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
            "Mordred": {
                "voice_type": "zh_male_beijingxiaoye_moon_bigtts",
                "encoding": "mp3",
                "speed_ratio": 1.0,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
            "Oberon": {
                "voice_type": "zh_female_wanqudashu_moon_bigtts",
                "encoding": "mp3",
                "speed_ratio": 1.0,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
        }
        
        # 从环境变量或配置文件加载API配置
        self.appid = os.getenv("TTS_APPID", "8748328986")
        self.token = os.getenv("TTS_TOKEN", "7wPh9Cf7dTTl4N94FfP3RmCzcQnCPJHm")
        self.cluster = os.getenv("TTS_CLUSTER", "2h3Vt087svOT6Q0LZOT0vI8jaeWRRlW5")
        self.host = "openspeech.bytedance.com"
        self.api_url = f"wss://{self.host}/api/v1/tts/ws_binary"
        
        # 默认请求头
        self.default_header = bytearray(b'\x11\x10\x11\x00')
        
        # 存储游戏角色映射
        self.game_roles = {}

    def init_app(self, app):
        self.app = app
        # 确保语音文件存储目录存在
        self.voice_dir = Path(app.config.get("DATA_DIR", "./data")) / "voice"
        self.voice_dir.mkdir(parents=True, exist_ok=True)

    def get_voice_file_path(self, battle_id: str, timestamp: str) -> Path:
        """获取语音文件路径"""
        game_voice_dir = self.voice_dir / str(battle_id)
        game_voice_dir.mkdir(exist_ok=True)
        return game_voice_dir / f"{timestamp}.mp3"

    def update_game_roles(self, role_data: Dict[str, str]):
        """更新游戏角色映射"""
        self.game_roles = role_data

    def get_role_by_player_id(self, player_id: str) -> str:
        """根据玩家ID获取角色"""
        return self.game_roles.get(str(player_id), "Knight")  # 默认使用骑士语音

    async def generate_voice(self, text: str, player_id: str, battle_id: str, timestamp: str) -> Optional[str]:
        """生成语音文件"""
        try:
            role = self.get_role_by_player_id(player_id)
            voice_settings = self.voice_settings.get(role, self.voice_settings["Knight"])
            output_path = self.get_voice_file_path(battle_id, timestamp)
            
            if output_path.exists():
                return str(output_path)

            request_json = {
                "app": {
                    "appid": self.appid,
                    "token": self.token,
                    "cluster": self.cluster
                },
                "user": {
                    "uid": str(uuid.uuid4())
                },
                "audio": {
                    "voice_type": voice_settings["voice_type"],
                    "encoding": "mp3",
                    "speed_ratio": voice_settings["speed_ratio"],
                    "volume_ratio": 1.0,
                    "pitch_ratio": voice_settings["pitch_ratio"],
                },
                "request": {
                    "reqid": str(uuid.uuid4()),
                    "text": text,
                    "text_type": "plain",
                    "operation": "submit"
                }
            }

            payload_bytes = str.encode(json.dumps(request_json))
            payload_bytes = gzip.compress(payload_bytes)
            full_client_request = bytearray(self.default_header)
            full_client_request.extend((len(payload_bytes)).to_bytes(4, 'big'))
            full_client_request.extend(payload_bytes)

            header = {"Authorization": f"Bearer; {self.token}"}
            async with websockets.connect(self.api_url, extra_headers=header, ping_interval=None) as ws:
                await ws.send(full_client_request)
                
                with open(output_path, "wb") as f:
                    while True:
                        res = await ws.recv()
                        if self._parse_response(res, f):
                            break

            return str(output_path)

        except Exception as e:
            if self.app:
                self.app.logger.error(f"语音生成失败: {str(e)}")
            return None

    def _parse_response(self, res: bytes, file) -> bool:
        """解析TTS响应"""
        protocol_version = res[0] >> 4
        header_size = res[0] & 0x0f
        message_type = res[1] >> 4
        message_type_specific_flags = res[1] & 0x0f
        serialization_method = res[2] >> 4
        message_compression = res[2] & 0x0f
        payload = res[header_size*4:]

        if message_type == 0xb:  # audio-only server response
            if message_type_specific_flags == 0:  # no sequence number as ACK
                return False
            else:
                sequence_number = int.from_bytes(payload[:4], "big", signed=True)
                payload_size = int.from_bytes(payload[4:8], "big", signed=False)
                payload = payload[8:]
                file.write(payload)
                return sequence_number < 0
        elif message_type == 0xf:  # error message
            code = int.from_bytes(payload[:4], "big", signed=False)
            msg_size = int.from_bytes(payload[4:8], "big", signed=False)
            error_msg = payload[8:]
            if message_compression == 1:
                error_msg = gzip.decompress(error_msg)
            error_msg = str(error_msg, "utf-8")
            if self.app:
                self.app.logger.error(f"TTS错误: {error_msg}")
            return True
        return True

# 创建全局TTS服务实例
tts_service = TTSService()