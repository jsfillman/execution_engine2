# execution_engine2 (ee2) release notes
=========================================
## 0.0.3.3
  * Change log appends from update to $push
  * Change first log linepos to position 0 instead of 1

## 0.0.3.2
  * Change 2 db state updates for startjob into 1
  * Rework Perms Model 
  * Stop Pymongo/Mongoengine clients on each request, and make it an instance variable for each worker thread.

## 0.0.3.1
  * Logging endpoint returns success value now
  * Added script to fix backfilled records
  * Logs transferred for held jobs ON_EXIT_OR_EVICT
  * Enabled job log monitor again

## 0.0.3
  * Fix Quay Build

## 0.0.2

  *  Fixed bug with service version displaying release instead of git commit
  *  Updated clients
  *  Update transfer script to handle failures

## 0.0.0 
  *  Module created by kb-sdk init
  *  We Were Young