import numpy as np
import base64
import json
import zlib
import logging
from typing import Dict, Any, Union
logger = logging.getLogger(__name__)
class KeyCompressionUtils:
    @staticmethod
    def compress_key_data(key_data: Dict) -> str:
        try:
            compressed_data = {}
            for key, value in key_data.items():
                if isinstance(value, np.ndarray):
                    compressed_data[key] = {
                        'type': 'ndarray',
                        'dtype': str(value.dtype),
                        'shape': value.shape,
                        'data': base64.b64encode(value.tobytes()).decode('utf-8')
                    }
                elif isinstance(value, list):
                    try:
                        arr = np.array(value)
                        compressed_data[key] = {
                            'type': 'ndarray',
                            'dtype': str(arr.dtype),
                            'shape': arr.shape,
                            'data': base64.b64encode(arr.tobytes()).decode('utf-8')
                        }
                    except:
                        compressed_data[key] = value
                elif isinstance(value, dict):
                    compressed_data[key] = value
                else:
                    compressed_data[key] = value
            json_str = json.dumps(compressed_data, separators=(',', ':'))
            compressed_bytes = zlib.compress(json_str.encode('utf-8'), level=9)
            result = base64.b64encode(compressed_bytes).decode('utf-8')
            logger.debug(f"密钥压缩: {len(json_str)} -> {len(result)} bytes ({len(result)/len(json_str)*100:.1f}%)")
            return result
        except Exception as e:
            logger.error(f"密钥数据压缩失败: {e}")
            return base64.b64encode(
                json.dumps(key_data).encode('utf-8')
            ).decode('utf-8')
    @staticmethod
    def decompress_key_data(compressed_data: str) -> Dict:
        try:
            compressed_bytes = base64.b64decode(compressed_data.encode('utf-8'))
            json_str = zlib.decompress(compressed_bytes).decode('utf-8')
            data = json.loads(json_str)
            restored_data = {}
            for key, value in data.items():
                if isinstance(value, dict) and value.get('type') == 'ndarray':
                    dtype = np.dtype(value['dtype'])
                    shape = tuple(value['shape'])
                    array_bytes = base64.b64decode(value['data'].encode('utf-8'))
                    restored_data[key] = np.frombuffer(array_bytes, dtype=dtype).reshape(shape)
                else:
                    restored_data[key] = value
            return restored_data
        except Exception as e:
            logger.warning(f"密钥解压缩失败，尝试原始格式: {e}")
            try:
                return json.loads(base64.b64decode(compressed_data).decode('utf-8'))
            except Exception as e2:
                logger.error(f"原始格式解码也失败: {e2}")
                raise ValueError(f"无法解码密钥数据: {e}")
    @staticmethod
    def is_compressed_format(data: str) -> bool:
        try:
            KeyCompressionUtils.decompress_key_data(data)
            return True
        except:
            return False
    @staticmethod
    def get_key_size_info(key_data: Union[str, Dict]) -> Dict[str, Any]:
        if isinstance(key_data, str):
            size_bytes = len(key_data.encode('utf-8'))
            is_compressed = KeyCompressionUtils.is_compressed_format(key_data)
            return {
                'size_bytes': size_bytes,
                'size_kb': round(size_bytes / 1024, 2),
                'is_compressed': is_compressed,
                'format': 'compressed' if is_compressed else 'base64'
            }
        elif isinstance(key_data, dict):
            json_str = json.dumps(key_data)
            size_bytes = len(json_str.encode('utf-8'))
            return {
                'size_bytes': size_bytes,
                'size_kb': round(size_bytes / 1024, 2),
                'is_compressed': False,
                'format': 'dict'
            }
        else:
            return {
                'size_bytes': 0,
                'size_kb': 0,
                'is_compressed': False,
                'format': 'unknown'
            }