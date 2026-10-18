FROM kms-dvadmin3-django:before-pool-sender-falcon-20261015-1807
COPY pqkds/ /backend/pqkds/
COPY tests/ /backend/tests/
