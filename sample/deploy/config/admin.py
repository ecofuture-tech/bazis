import os

import psutil


reload = False
preload_app = False
threads = 2
error_logfile = '-'
capture_output = True
worker_tmp_dir = '/dev/shm'
forwarded_allow_ips = '*'
max_requests = 10000
max_requests_jitter = int(max_requests / 10) + 1
workers = int(os.getenv('_BS_APP_GUNICORN_WORKERS', psutil.cpu_count()))
bind = ['0.0.0.0:' + os.getenv('BS_ADMIN_PORT', 8081)]
