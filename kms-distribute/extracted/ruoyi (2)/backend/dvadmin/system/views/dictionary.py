from rest_framework import serializers
from rest_framework.views import APIView
from application import dispatch
from dvadmin.system.models import Dictionary
from dvadmin.utils.json_response import SuccessResponse
from dvadmin.utils.serializers import CustomModelSerializer
from dvadmin.utils.viewset import CustomModelViewSet
class DictionarySerializer(CustomModelSerializer):
    class Meta:
        model = Dictionary
        fields = "__all__"
        read_only_fields = ["id"]
class DictionaryCreateUpdateSerializer(CustomModelSerializer):
    value = serializers.CharField(max_length=100)
    def validate_value(self, value):
        initial_data = self.initial_data
        parent = initial_data.get('parent',None)
        if parent is None:
            unique =  Dictionary.objects.filter(value=value).exists()
            if unique:
                raise serializers.ValidationError("字典编号不能重复")
        return value
    class Meta:
        model = Dictionary
        fields = '__all__'
class DictionaryViewSet(CustomModelViewSet):
    queryset = Dictionary.objects.all()
    serializer_class = DictionarySerializer
    create_serializer_class = DictionaryCreateUpdateSerializer
    extra_filter_class = []
    search_fields = ['label']
    def get_queryset(self):
        if self.action =='list':
            params = self.request.query_params
            parent = params.get('parent', None)
            if params:
                if parent:
                    queryset = self.queryset.filter(parent=parent)
                else:
                    queryset = self.queryset.filter(parent__isnull=True)
            else:
                queryset = self.queryset.filter(parent__isnull=True)
            return queryset
        else:
            return self.queryset
class InitDictionaryViewSet(APIView):
    authentication_classes = []
    permission_classes = []
    queryset = Dictionary.objects.all()
    def get(self, request):
        dictionary_key = self.request.query_params.get('dictionary_key')
        if dictionary_key:
            if dictionary_key == 'all':
                data = [ele for ele in dispatch.get_dictionary_config().values()]
                if not data:
                    dispatch.refresh_dictionary()
                    data = [ele for ele in dispatch.get_dictionary_config().values()]
            else:
                data = self.queryset.filter(parent__value=dictionary_key, status=True).values('label', 'value', 'type',
                                                                                              'color')
            return SuccessResponse(data=data, msg="获取成功")
        return SuccessResponse(data=[], msg="获取成功")