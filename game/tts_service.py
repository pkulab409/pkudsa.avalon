# coding=utf-8

import os
import json
import gzip
import uuid
import asyncio
import hashlib
from typing import Dict, Optional
from pathlib import Path

# 使用新的asyncio API而不是legacy API
try:
    from websockets.asyncio.client import connect
except ImportError:
    # 如果新API不可用，回退到legacy API
    from websockets.legacy.client import connect as legacy_connect
    
    # 创建一个包装器来统一API
    async def connect(uri, **kwargs):
        # 将additional_headers转换为extra_headers用于legacy API
        if 'additional_headers' in kwargs:
            kwargs['extra_headers'] = kwargs.pop('additional_headers')
        return await legacy_connect(uri, **kwargs)


class TTSService:
    def __init__(self, app=None):
        self.app = app
        self.voice_settings = {
            "Merlin": {
                "voice_type": "ICL_zh_male_guiyishenmi_tob",
                "encoding": "mp3",
                "speed_ratio": 1.2,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
            "Percival": {
                "voice_type": "ICL_zh_male_guzhibingjiao_tob",
                "encoding": "mp3",
                "speed_ratio": 1.2,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
            "Knight": {
                "voice_type": "zh_male_yangguangqingnian_emo_v2_mars_bigtts",
                "encoding": "mp3",
                "speed_ratio": 1.2,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
            "Morgana": {
                "voice_type": "zh_female_meilinvyou_emo_v2_mars_bigtts",
                "encoding": "mp3",
                "speed_ratio": 1.4,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
            "Mordred": {
                "voice_type": "zh_male_beijingxiaoye_moon_bigtts",
                "encoding": "mp3",
                "speed_ratio": 1.2,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
            "Oberon": {
                "voice_type": "ICL_zh_male_shaonianjiangjun_tob",
                "encoding": "mp3",
                "speed_ratio": 1.2,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
        }

        # 从环境变量或配置文件加载API配置
        self.appid = os.getenv("TTS_APPID", "8748328986")
        self.token = os.getenv("TTS_TOKEN", "7wPh9Cf7dTTl4N94FfP3RmCzcQnCPJHm")
        self.cluster = os.getenv("TTS_CLUSTER", "volcano_tts")
        self.host = "openspeech.bytedance.com"
        self.api_url = f"wss://{self.host}/api/v1/tts/ws_binary"

        # 默认请求头（参考demo）
        self.default_header = bytearray(b"\x11\x10\x11\x00")

        # 存储游戏角色映射
        self.game_roles = {}

    def init_app(self, app):
        self.app = app
        # 确保语音文件存储目录存在
        self.voice_dir = Path(app.config.get("DATA_DIR", "./data")) / "voice"
        self.voice_dir.mkdir(parents=True, exist_ok=True)

    def get_voice_file_path(self, battle_id: str, text: str, player_id: str) -> Path:
        """获取语音文件路径，使用文本和玩家ID的哈希值作为文件名"""
        game_voice_dir = self.voice_dir / str(battle_id)
        game_voice_dir.mkdir(exist_ok=True)
        
        # 使用文本内容和玩家ID生成唯一的文件名
        text_hash = hashlib.sha256(f"{text}_{player_id}".encode('utf-8')).hexdigest()[:12]
        filename = f"player_{player_id}_{text_hash}.mp3"
        return game_voice_dir / filename

    def update_game_roles(self, role_data: Dict[str, str]):
        """更新游戏角色映射"""
        self.game_roles = role_data

    def get_role_by_player_id(self, player_id: str) -> str:
        """根据玩家ID获取角色"""
        return self.game_roles.get(str(player_id), "Knight")  # 默认使用骑士语音

    def generate_voice_sync(self, text: str, player_id: str, battle_id: str, app_context=None) -> Optional[str]:
        """同步生成语音文件的包装器"""
        try:
            # 在新的事件循环中运行异步方法
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.generate_voice(text, player_id, battle_id, app_context)
                )
                return result
            finally:
                loop.close()
        except Exception as e:
            # 使用传入的app_context或self.app来记录错误
            if app_context:
                app_context.logger.error(f"同步语音生成失败: {str(e)}")
            elif self.app:
                self.app.logger.error(f"同步语音生成失败: {str(e)}")
            else:
                print(f"同步语音生成失败: {str(e)}")
            return None

    async def generate_voice(
        self, text: str, player_id: str, battle_id: str, app_context=None
    ) -> Optional[str]:
        """生成语音文件"""
        try:
            role = self.get_role_by_player_id(player_id)
            voice_settings = self.voice_settings.get(
                role, self.voice_settings["Knight"]
            )
            output_path = self.get_voice_file_path(battle_id, text, player_id)

            # 如果文件已存在，直接返回路径
            if output_path.exists():
                return str(output_path)

            # 构建请求JSON（严格按照官方文档格式）
            request_json = {
                "app": {
                    "appid": self.appid,
                    "token": self.token,  # 官方文档确认直接使用token
                    "cluster": self.cluster,
                },
                "user": {"uid": str(uuid.uuid4())},
                "audio": {
                    "voice_type": voice_settings["voice_type"],
                    "encoding": "mp3",
                    "speed_ratio": voice_settings["speed_ratio"],
                    "volume_ratio": voice_settings["volume_ratio"],
                    "pitch_ratio": voice_settings["pitch_ratio"],
                },
                "request": {
                    "reqid": str(uuid.uuid4()),
                    "text": text,
                    "text_type": "plain",  # 官方文档中的参数
                    "operation": "submit",  # 官方文档要求使用submit
                },
            }

            # 构建请求数据（参考官方文档的二进制协议）
            payload_bytes = str.encode(json.dumps(request_json))
            payload_bytes = gzip.compress(payload_bytes)  # 压缩payload
            full_client_request = bytearray(self.default_header)
            full_client_request.extend((len(payload_bytes)).to_bytes(4, "big"))  # payload size
            full_client_request.extend(payload_bytes)  # payload

            # 构建请求头（严格按照官方文档格式）
            # 官方文档明确要求：headers["Authorization"] = "Bearer;${token}"
            header = {"Authorization": f"Bearer;{self.token}"}  # 注意：Bearer后面直接跟分号，没有空格
            
            # 使用新的asyncio API和additional_headers参数
            async with connect(
                self.api_url, additional_headers=header, ping_interval=None
            ) as ws:
                await ws.send(full_client_request)

                with open(output_path, "wb") as f:
                    while True:
                        res = await ws.recv()
                        done = self._parse_response(res, f, app_context)
                        if done:
                            break

            # 验证文件是否成功生成
            if output_path.exists() and output_path.stat().st_size > 0:
                return str(output_path)
            else:
                error_msg = f"语音文件生成失败或文件为空: {output_path}"
                if app_context:
                    app_context.logger.error(error_msg)
                elif self.app:
                    self.app.logger.error(error_msg)
                else:
                    print(error_msg)
                return None

        except Exception as e:
            error_msg = f"语音生成失败: {str(e)}"
            if app_context:
                app_context.logger.error(error_msg)
            elif self.app:
                self.app.logger.error(error_msg)
            else:
                print(error_msg)
            return None

    def _parse_response(self, res: bytes, file, app_context=None) -> bool:
        """解析TTS响应（参考demo）"""
        try:
            protocol_version = res[0] >> 4
            header_size = res[0] & 0x0F
            message_type = res[1] >> 4
            message_type_specific_flags = res[1] & 0x0F
            serialization_method = res[2] >> 4
            message_compression = res[2] & 0x0F
            reserved = res[3]
            header_extensions = res[4:header_size*4]
            payload = res[header_size * 4 :]

            if message_type == 0xB:  # audio-only server response
                if message_type_specific_flags == 0:  # no sequence number as ACK
                    return False
                else:
                    sequence_number = int.from_bytes(payload[:4], "big", signed=True)
                    payload_size = int.from_bytes(payload[4:8], "big", signed=False)
                    payload = payload[8:]
                    file.write(payload)
                    return sequence_number < 0  # 当sequence_number < 0时表示最后一个包
            elif message_type == 0xF:  # error message
                code = int.from_bytes(payload[:4], "big", signed=False)
                msg_size = int.from_bytes(payload[4:8], "big", signed=False)
                error_msg = payload[8:]
                if message_compression == 1:
                    error_msg = gzip.decompress(error_msg)
                error_msg = str(error_msg, "utf-8")
                
                error_log = f"TTS服务器错误 (代码: {code}): {error_msg}"
                if app_context:
                    app_context.logger.error(error_log)
                elif self.app:
                    self.app.logger.error(error_log)
                else:
                    print(error_log)
                return True
            elif message_type == 0xC:  # frontend server response
                msg_size = int.from_bytes(payload[:4], "big", signed=False)
                payload = payload[4:]
                if message_compression == 1:
                    payload = gzip.decompress(payload)
                
                info_log = f"TTS前端消息: {payload}"
                if app_context:
                    app_context.logger.info(info_log)
                elif self.app:
                    self.app.logger.info(info_log)
                else:
                    print(info_log)
                return False
            else:
                error_log = f"未定义的消息类型: {message_type}"
                if app_context:
                    app_context.logger.error(error_log)
                elif self.app:
                    self.app.logger.error(error_log)
                else:
                    print(error_log)
                return True
        except Exception as e:
            error_log = f"解析TTS响应时出错: {str(e)}"
            if app_context:
                app_context.logger.error(error_log)
            elif self.app:
                self.app.logger.error(error_log)
            else:
                print(error_log)
            return True


# 创建全局TTS服务实例
tts_service = TTSService()
