from apscheduler.events import (
    EVENT_ALL_JOBS_REMOVED,
    EVENT_EXECUTOR_ADDED,
    EVENT_EXECUTOR_REMOVED,
    EVENT_JOB_ADDED,
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MAX_INSTANCES,
    EVENT_JOB_MISSED,
    EVENT_JOB_MODIFIED,
    EVENT_JOB_REMOVED,
    EVENT_JOB_SUBMITTED,
    EVENT_JOBSTORE_ADDED,
    EVENT_JOBSTORE_REMOVED,
    EVENT_SCHEDULER_PAUSED,
    EVENT_SCHEDULER_RESUMED,
    EVENT_SCHEDULER_SHUTDOWN,
    EVENT_SCHEDULER_START,
)
from loguru import logger


def my_listener(event) -> None:
    """
    EVENT_SCHEDULER_START = 1
    EVENT_SCHEDULER_SHUTDOWN = 2
    EVENT_SCHEDULER_PAUSED = 4
    EVENT_SCHEDULER_RESUMED = 8
    EVENT_EXECUTOR_ADDED = 16
    EVENT_EXECUTOR_REMOVED = 32
    EVENT_JOBSTORE_ADDED = 64
    EVENT_JOBSTORE_REMOVED = 128
    EVENT_ALL_JOBS_REMOVED = 256
    EVENT_JOB_ADDED = 512
    EVENT_JOB_REMOVED = 1024
    EVENT_JOB_MODIFIED = 2048
    EVENT_JOB_EXECUTED = 4096
    EVENT_JOB_ERROR = 8192
    EVENT_JOB_MISSED = 16384
    EVENT_JOB_SUBMITTED = 32768
    EVENT_JOB_MAX_INSTANCES = 65536

    """
    event_code: int = event.code
    if event_code == EVENT_SCHEDULER_START:
        logger.info("The scheduler was started")
    if event_code == EVENT_SCHEDULER_SHUTDOWN:
        logger.info("The scheduler was shut down")
    if event_code == EVENT_SCHEDULER_PAUSED:
        logger.debug("Job processing in the scheduler was paused")
    if event_code == EVENT_SCHEDULER_RESUMED:
        logger.debug("Job processing in the scheduler was resumed")
    if event_code == EVENT_EXECUTOR_ADDED:
        logger.debug("An executor was added to the scheduler")
    if event_code == EVENT_EXECUTOR_REMOVED:
        logger.debug("An executor was removed to the scheduler")
    if event_code == EVENT_JOBSTORE_ADDED:
        logger.debug("A job store was added to the scheduler")
    if event_code == EVENT_JOBSTORE_REMOVED:
        logger.debug("A job store was removed from the scheduler")
    if event_code == EVENT_ALL_JOBS_REMOVED:
        logger.debug("All jobs were removed from either all job stores or one particular job store")
    if event_code == EVENT_JOB_ADDED:
        logger.debug("A job was added to a job store")
    if event_code == EVENT_JOB_REMOVED:
        logger.debug("A job was removed from a job store")
    if event_code == EVENT_JOB_MODIFIED:
        logger.debug("A job was modified from outside the scheduler")
    if event_code == EVENT_JOB_SUBMITTED:
        logger.debug("A job was submitted to its executor to be run")
    if event_code == EVENT_JOB_MAX_INSTANCES:
        logger.error(
            "A job being submitted to its executor was not accepted by"
            " the executor because the job has already reached"
            " its maximum concurrently executing instances"
        )
    if event_code == EVENT_JOB_EXECUTED:
        logger.debug("A job was executed successfully")
    if event_code == EVENT_JOB_ERROR:
        logger.error("A job raised an exception during execution")
    if event_code == EVENT_JOB_MISSED:
        logger.error("A job's execution was missed")
