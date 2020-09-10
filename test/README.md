Step 1)
* `docker build . -t kbase/execution_engine2:test`

Step 2)
* Go to the execution_engine2/test/dockerfiles/condor directory and run
* `docker-compose up -d`
* You may need to edit the mount point to mount your local disk as a docker volume


Step 3)
* Make sure you edit the test/deploy.cfg  to point the the container name. 
* This will automatically replace localhost
`mongo-in-docker-compose = condor_mongo_1`

Step 4)
* Go to /Users/YourName/execution_engine2 or wherever you put it and run the commands you see in the .travis.yml
* make setup-database
* make test

NOTES: --no-cov is required for pycharm debugger