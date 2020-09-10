#!/usr/bin/env bash
set -x

HOME=$(pwd)
export HOME
# Detect if we are running at NERSC and load some customization
# Probably better ways to deal with this but this is good enough.
if [ -e /global/homes/k/kbaserun/.local_settings ] ; then
   HOME=/global/homes/k/kbaserun
   . $HOME/.local_settings $1 $2
fi

debug_dir="debug"
runner_logs="runner_logs"
mkdir ${debug_dir}
mkdir ${runner_logs}
runner_logs=$(readlink -f runner_logs)
debug_dir=$(readlink -f debug_dir)

env >"${debug_dir}/envf"
{
  echo "export CLIENTGROUP=$CLIENTGROUP "
  echo "export PYTHON_EXECUTABLE=$PYTHON_EXECUTABLE "
  echo "export KB_ADMIN_AUTH_TOKEN=$KB_ADMIN_AUTH_TOKEN "
  echo "export KB_AUTH_TOKEN=$KB_AUTH_TOKEN "
  echo "export DOCKER_JOB_TIMEOUT=$DOCKER_JOB_TIMEOUT "
  echo "export CONDOR_ID=$CONDOR_ID "
  echo "export JOB_ID=$JOB_ID "
  echo "export DELETE_ABANDONED_CONTAINERS=$DELETE_ABANDONED_CONTAINERS "
  echo "export DEBUG_MODE=$DEBUG_MODE "
} >>"${debug_dir}/env_file"

${PYTHON_EXECUTABLE} -V "${debug_dir}/pyversion"

JOB_ID=$1
EE2_ENDPOINT=$2
KBASE_ENDPOINT=$EE2_ENDPOINT
export KBASE_ENDPOINT

tar -xf JobRunner.tgz && cd JobRunner && cp scripts/*.py . && chmod +x ./*.py

${PYTHON_EXECUTABLE} ./jobrunner.py "${JOB_ID}" "${EE2_ENDPOINT}" &
pid=$!

${PYTHON_EXECUTABLE} ./monitor_jobrunner_logs.py "${JOB_ID}" "${EE2_ENDPOINT}" "${pid}" &
pid2=$!

trap '{ kill $pid }' SIGTERM
wait ${pid}
EXIT_CODE=$?

# Deprecated these in favor of moving them back to ee2 container.
#LOG_DIR="../../../logs/${JOB_ID}"
#mkdir -p "${LOG_DIR}"
#cp "${runner_logs}/${JOB_ID}".out "${LOG_DIR}/".
#cp "${runner_logs}/${JOB_ID}".err "${LOG_DIR}/"
kill -9 $pid2
exit ${EXIT_CODE}
