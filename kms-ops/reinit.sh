#!/bin/bash
echo "Reinitializing DB"
mysql -uroot -proot123456 --default-character-set=utf8mb4 kms < /docker-entrypoint-initdb.d/1.sql
mysql -uroot -proot123456 --default-character-set=utf8mb4 kms < /docker-entrypoint-initdb.d/2.sql
mysql -uroot -proot123456 --default-character-set=utf8mb4 kms < /docker-entrypoint-initdb.d/3.sql
mysql -uroot -proot123456 --default-character-set=utf8mb4 kms < /docker-entrypoint-initdb.d/4.sql
mysql -uroot -proot123456 --default-character-set=utf8mb4 kms < /docker-entrypoint-initdb.d/5.sql
mysql -uroot -proot123456 --default-character-set=utf8mb4 kms < /docker-entrypoint-initdb.d/6_permission_request.sql
mysql -uroot -proot123456 --default-character-set=utf8mb4 kms < /docker-entrypoint-initdb.d/7_add_permission_menu.sql
mysql -uroot -proot123456 --default-character-set=utf8mb4 kms < /docker-entrypoint-initdb.d/8_add_permission_menu_simple.sql
mysql -uroot -proot123456 --default-character-set=utf8mb4 kms < /docker-entrypoint-initdb.d/9_alter_permission_request_for_system_scope.sql
mysql -uroot -proot123456 --default-character-set=utf8mb4 kms < /docker-entrypoint-initdb.d/10_key_distribute_record.sql
mysql -uroot -proot123456 --default-character-set=utf8mb4 kms < /docker-entrypoint-initdb.d/11_fix_missing_menu_parents.sql
echo "import complete"
