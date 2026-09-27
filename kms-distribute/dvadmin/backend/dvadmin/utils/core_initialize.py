import logging
import os
import json
from application.settings import BASE_DIR

logger = logging.getLogger(__name__)

class CoreInitialize:
    def __init__(self, app=None, reset=False):
        self.app = app
        self.reset = reset
        logger.info(f"初始化 {app}, reset={reset}")

    def init_base(self, serializer, unique_fields=None):
        """
        初始化数据的基础方法
        :param serializer: 序列化器类
        :param unique_fields: 唯一字段列表，用于判断数据是否已存在
        """
        if not self.app:
            return

        model = serializer.Meta.model
        model_name = model._meta.model_name

        # 尝试多个可能的路径
        possible_paths = [
            os.path.join(BASE_DIR, f'init_{model_name}.json'),
            os.path.join(BASE_DIR, self.app.replace('.', os.sep), 'fixtures', f'init_{model_name}.json'),
        ]

        json_file = None
        for path in possible_paths:
            if os.path.exists(path):
                json_file = path
                break

        if not json_file:
            logger.warning(f"初始化文件不存在: {model_name}")
            return

        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data_list = json.load(f)

            logger.info(f"开始初始化 {model_name}, 共 {len(data_list)} 条数据")

            for data in data_list:
                try:
                    data['reset'] = self.reset
                    if self.reset:
                        if unique_fields:
                            filter_dict = {field: data.get(field) for field in unique_fields if field in data}
                            model.objects.filter(**filter_dict).delete()
                        ser = serializer(data=data, request=None)
                        if ser.is_valid():
                            ser.save()
                        else:
                            logger.error(f"数据验证失败: {ser.errors}")
                    else:
                        if unique_fields:
                            filter_dict = {field: data.get(field) for field in unique_fields if field in data}
                            if not model.objects.filter(**filter_dict).exists():
                                ser = serializer(data=data, request=None)
                                if ser.is_valid():
                                    ser.save()
                                else:
                                    logger.error(f"数据验证失败: {ser.errors}")
                        else:
                            ser = serializer(data=data, request=None)
                            if ser.is_valid():
                                ser.save()
                            else:
                                logger.error(f"数据验证失败: {ser.errors}")
                except Exception as e:
                    logger.warning(f"跳过数据: {e}")

            logger.info(f"{model_name} 初始化完成")
        except Exception as e:
            logger.error(f"初始化 {model_name} 失败: {e}")
