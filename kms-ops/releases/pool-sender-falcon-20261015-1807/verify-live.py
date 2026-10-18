from pqkds.models import Node
from pqkds.serializers import NodeListSerializer

nodes = list(Node.objects.all())
serializer = NodeListSerializer()
canonical = sum(bool(node.falcon_sign_public_key) for node in nodes)
ready = sum(serializer.get_falcon_key_ready(node) for node in nodes)
assert all(serializer.get_falcon_key_ready(node) == bool(node.falcon_sign_public_key or node.falcon_public_key) for node in nodes)
print(f'FALCON_READY_OK nodes={len(nodes)} canonical_ready={canonical} displayed_ready={ready}')
