#!/bin/env bash
set -e
set -x
lib_dir=/kb/module/lib
wsgi_dir=$lib_dir/execution_engine2


# Set the number of gevent workers to number of cores * 2 + 1
# See: http://docs.gunicorn.org/en/stable/design.html#how-many-workers
calc_workers="$(($(nproc) * 2 + 1))"
# Use the WORKERS environment variable, if present
workers=${WORKERS:-$calc_workers}

export PYTHONPATH=$lib_dir:$wsgi_dir:$PYTHONPATH

# Set up the purge held jobs script
bash /kb/module/scripts/purge_held_jobs.sh >> purge.log 2>&1 &

# Config the tmp reaper
sed -i "s|SHOWWARNING=true|SHOWWARNING=false|" /etc/tmpreaper.conf
sed -i "s|TMPREAPER_DIRS='/tmp/.'|TMPREAPER_DIRS='/condor_shared/runner_logs /condor_shared/cluster_logs'|" /etc/tmpreaper.conf


gunicorn \
  --user kbase \
  --worker-class gevent \
  --timeout 1800 \
  --workers $workers  \
  --bind :5000 \
  ${DEVELOPMENT:+"--reload"} \
  execution_engine2Server:application