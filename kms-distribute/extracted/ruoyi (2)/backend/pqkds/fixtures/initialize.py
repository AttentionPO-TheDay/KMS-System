from dvadmin.utils.core_initialize import CoreInitialize
from dvadmin.system.fixtures.initSerializer import MenuInitSerializer


class Initialize(CoreInitialize):
    def init_menu(self):
        self.init_base(MenuInitSerializer, unique_fields=['name', 'web_path', 'component', 'component_name'])

    def run(self):
        self.init_menu()

