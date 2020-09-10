import logging
from pymongo import MongoClient
import subprocess


class MongoTestHelper:
    @classmethod
    def _start_service(self, cfg):
        if not cfg["start-local-mongo"] == "1":
            return

        logging.info("starting mongod service")

        logging.info("running sudo service mongodb start")
        pipe = subprocess.Popen(
            "sudo service mongodb start",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = pipe.communicate()

        logging.info(stdout)
        logging.info(stderr)

        logging.info("running mongod --version")
        pipe = subprocess.Popen(
            "mongod --version",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout = pipe.communicate()

        logging.info(stdout)

    @classmethod
    def _get_default_jobs(self):

        row_jobs = [
            [
                "KBH_68020",
                "b753774f-0bbd-4b96-9202-89b0c70bf31c",
                "interleaved.fastq",
                "shock",
                "http://ci.kbase.us:7044/",
                None,
                None,
                "tgu2",
                "2016-12-20 10:18:17",
            ],
            [
                "KBH_68021",
                "4cb26117-9793-4354-98a6-926c02a7bd0e",
                "SP1.fq.gz",
                "shock",
                "https://ci.kbase.us/services/shock-api",
                "2c40e80ae4fb981541fc6918035c8707",
                None,
                "tgu2",
                "2016-12-21 10:34:20",
            ],
            [
                "KBH_68022",
                "cadf4bd8-7d95-4edd-994c-b50e29c25e50",
                "SP1.fq.gz",
                "shock",
                "https://ci.kbase.us/services/shock-api",
                "e47f6adcaa33436ad0746fe9f936e359",
                None,
                "tgu2",
                "2016-12-21 10:57:06",
            ],
            [
                "KBH_68023",
                "d24188ed-83ff-4939-9dc2-84cc758738a3",
                "SP1.fq.gz",
                "shock",
                "https://ci.kbase.us/services/shock-api",
                "1da5481d162ca923c3ad27722ffdd377",
                None,
                "tgu2",
                "2016-12-21 11:12:29",
            ],
            [
                "KBH_68024",
                "acd1d64b-da98-467f-b29c-baca2862dd23",
                "SP1.fq.gz",
                "shock",
                "https://ci.kbase.us/services/shock-api",
                "43966480eabf5848fdc6046ba4214bee",
                None,
                "tgu2",
                "2016-12-21 11:18:57",
            ],
            [
                "KBH_68025",
                "f973cbd3-8881-4281-afef-a8419629e813",
                "SP1.fq.gz",
                "shock",
                "https://ci.kbase.us/services/shock-api",
                "c374414a78a20feb716ea71c0ecf0a58",
                None,
                "tgu2",
                "2016-12-21 11:24:06",
            ],
            [
                "KBH_68026",
                "a676f82a-adc5-478e-b85a-d8244eae965e",
                "SP1.fq.gz",
                "shock",
                "https://ci.kbase.us/services/shock-api",
                "79cc52fff3c465681d162ce3caa6e672",
                None,
                "tgu2",
                "2016-12-21 11:29:37",
            ],
            [
                "KBH_68027",
                "f4113d56-9840-4811-b32d-4ae09523389a",
                "SP1.fq.gz",
                "shock",
                "https://ci.kbase.us/services/shock-api",
                "15aa9c1535b0da2158f169c748ee2a11",
                None,
                "tgu2",
                "2016-12-21 21:41:08",
            ],
            [
                "KBH_68028",
                "a31db49f-447c-4fff-96d5-2981166c0b9b",
                "tmp_fastq.fq.gz",
                "shock",
                "https://ci.kbase.us/services/shock-api",
                "f78e79df067806daa1f0946ddc790b53",
                None,
                "tgu2",
                "2016-12-21 21:41:36",
            ],
            [
                "KBH_68029",
                "7a2ff7c8-d87d-4c25-ad25-5f85ea794afa",
                "tmp_fastq.fq.gz",
                "shock",
                "https://ci.kbase.us/services/shock-api",
                "05361e0506af15be6701b175adbb23e4",
                None,
                "tgu2",
                "2016-12-21 21:45:39",
            ],
        ]

        key_names = [
            "_id",
            "hid",
            "id",
            "file_name",
            "type",
            "url",
            "remote_md5",
            "remote_sha1",
            "created_by",
            "creation_date",
        ]

        jobs = list()
        for job in row_jobs:
            job_doc = dict()
            job_doc.update({key_names[0]: job[0]})
            for idx, h in enumerate(job):
                job_doc.update({key_names[idx + 1]: h})

            jobs.append(job_doc)

        return jobs

    def __init__(self, cfg):
        self.cfg = cfg
        self._start_service(cfg)

    def create_test_db(self, db="ee2", col="ee2_jobs"):

        logging.info("creating collection and dbs")
        cfg = self.cfg
        logging.info(cfg)
        try:
            my_client = MongoClient(cfg["mongo-host"], int(cfg["mongo-port"]))
            my_client.ee2.command(
                "createUser",
                cfg["mongo-user"],
                pwd=cfg["mongo-password"],
                roles=["readWrite"],
            )
        except Exception:
            pass

        my_client = MongoClient(
            cfg["mongo-host"],
            int(cfg["mongo-port"]),
            username=cfg["mongo-user"],
            password=cfg["mongo-password"],
            authSource=db,
            authMechanism="DEFAULT",
        )

        my_db = my_client[db]
        my_collection = my_db[col]
        my_collection.delete_many({})

        # jobs = self._get_default_jobs()
        # my_collection.insert_many(jobs)

        logging.info("created db: {}".format(my_client.list_database_names()))

        return my_collection
