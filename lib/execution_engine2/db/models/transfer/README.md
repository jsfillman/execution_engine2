# How to transfer ujs records or log records

##### ssh into your environment's njs_wrapper container
* ssh into ci.kbase.us
* docker ps | grep njs
* docker exec -it -u 0 <container_id> bash
```
cd ~;
git clone https://github.com/kbase/execution_engine2
cd execution_engine2/lib/execution_engine2/db/models/transfer/
cp ../models.py .
source /opt/rh/rh-python36/enable
* Set the variable jobs_database_name in the script
chmod +x transfer_ujs_njs.py && ./transfer_ujs_njs.py
chmod +x transfer_logs.py && ./transfer_logs.py
```


# Rollback from ee2 to njs/ujs

```
cd execution_engine2/lib/execution_engine2/db/models/transfer/
source /opt/rh/rh-python36/enable

python rollback_db.py test_roll_back  # test rollback, create njs/ujs jobs and logs records in xx_test_rb collection from ee2_jobs/logs

python rollback_db.py  # rollback ee2 records created 24 hrs ago

## in order to rollback full ee2 DB, comment ```cut_off_date = datetime.today() - timedelta(days=1)``` in main()
```
