FROM kms-dvadmin3-django:before-node-permission-20261015
COPY pqkds/ /backend/pqkds/
COPY tests/ /backend/tests/
